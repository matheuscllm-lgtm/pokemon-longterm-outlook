"""Score de potencial de LONGO PRAZO (0-100) por carta — heurística declarada.

O score soma 4 componentes de 0-25, cada um com racional explícito (a tabela
final mostra o racional por linha). NÃO é previsão de preço nem conselho de
investimento: é uma triagem ordenável pra ajudar o operador a olhar primeiro
o que tem mais características historicamente associadas a valorização.
Quem decide capital é o operador.

Componentes:
  1. PERSONAGEM  (0-25) — apelo/demanda perene do personagem (Pokémon OU
       treinador), por tier curado: S=25, A=18, B=12, fora da lista=8.
       Inclui treinadores (Marnie, Lillie, Iono...): SIR/full-art de treinadora
       valoriza tanto quanto de Pokémon e antes ficava de fora (caía em 8).
  2. RARIDADE    (0-25) — alt-art/SIR > IR > gold/secret > ultra > resto.
       Limitação conhecida: na era SWSH o pokemontcg.io não distingue
       "alt art" de ultra/secret comum pela raridade — alt arts SWSH ficam
       subpontuadas aqui (o componente de preço compensa parcialmente).
  3. SUPPLY      (0-25) — set fora de impressão (idade) = oferta encolhendo.
       Sets com reprint forte (151, Prismatic...) têm teto rebaixado.
  4. PREÇO       (0-25) — sweet spot $15-120: demanda comprovada com espaço
       pra crescer; bulk <$5 não tem liquidez; >$300 já está precificado.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .notorious import match_notorious, tier_points

# Sets com reprint contínuo/forte — supply não encolhe com a idade como o
# normal. Teto do componente SUPPLY rebaixado (cap 12) + flag na tabela.
# IDs = pokemontcg.io; NAME_PARTS = match por substring no nome do set
# (cobre a fonte tcgcsv, cujos ids são groupIds numéricos do TCGPlayer).
HEAVY_REPRINT_SET_IDS = {
    "sv3pt5",    # 151
    "sv4pt5",    # Paldean Fates
    "sv8pt5",    # Prismatic Evolutions
    "swsh35",    # Champion's Path
    "swsh45",    # Shining Fates
    "swsh12pt5", # Crown Zenith
    "cel25",     # Celebrations
}
HEAVY_REPRINT_NAME_PARTS = (
    "151", "Paldean Fates", "Prismatic Evolutions", "Champion's Path",
    "Shining Fates", "Crown Zenith", "Celebrations", "Ascended Heroes",
)

# Sets ESPECIAIS ficam fora da numeração da era no TCGPlayer ("SV: 151",
# "ME: Ascended Heroes"), ao contrário dos mains numerados ("SV01:", "ME01:").
# Especiais são impressos em massa e por muito tempo — a oferta não encolhe
# como a de um main que sai de catálogo. Detectar pelo padrão do nome elimina a
# manutenção manual da lista acima (que já tinha deixado "Ascended Heroes" de
# fora) e cobre a fonte tcgcsv (a default). A lista continua servindo a fonte
# ptcg, cujos nomes não trazem o prefixo de era. Stance conservador de propósito:
# na dúvida, NÃO creditamos oferta encolhendo a um set que segue sendo impresso.
SPECIAL_SET_PREFIX_RE = re.compile(r"^(SV|SWSH|ME):")


def is_heavy_reprint(set_id: str, set_name: str) -> bool:
    name = set_name or ""
    return (set_id in HEAVY_REPRINT_SET_IDS
            or any(part in name for part in HEAVY_REPRINT_NAME_PARTS)
            or bool(SPECIAL_SET_PREFIX_RE.match(name)))


def rarity_points(rarity: str) -> int:
    """Pesos por grupo de raridade (match por substring, nomes variam por era)."""
    r = (rarity or "").lower()
    if "special illustration" in r:
        return 25
    if "illustration" in r:
        return 20
    if "trainer gallery" in r or "character" in r:
        return 16
    # era Mega: "Mega Attack Rare" = arte de ataque do Mega ex (tier full-art
    # premium, abaixo de SIR; ~nível Illustration Rare no mercado). Sem esta
    # regra cairia no default (3 = comum) — era o bug que subpontuava esses ex.
    if "attack" in r:
        return 16
    if "hyper" in r or "secret" in r or "rainbow" in r:
        return 14
    if "amazing" in r or "radiant" in r or "shiny" in r:
        return 14
    if "vmax" in r or "vstar" in r or "ultra" in r:
        return 12
    if "ace spec" in r:
        return 10
    if "double rare" in r or r == "rare holo v":
        return 6
    return 3


def supply_points(release: date, today: date, heavy_reprint: bool) -> int:
    months = (today.year - release.year) * 12 + (today.month - release.month)
    if months >= 36:
        pts = 25
    elif months >= 24:
        pts = 22
    elif months >= 18:
        pts = 18
    elif months >= 12:
        pts = 12
    elif months >= 6:
        pts = 7
    else:
        pts = 3
    return min(pts, 12) if heavy_reprint else pts


def price_points(market_usd: float) -> int:
    if market_usd < 5:
        return 5
    if market_usd < 15:
        return 12
    if market_usd < 40:
        return 20
    if market_usd < 120:
        return 25
    if market_usd < 300:
        return 18
    return 12


# ── Modo graded (operador que só compra PSA 10) ──────────────────────────────
# As faixas raw acima são a MESMA lógica econômica ("espaço pra crescer com
# liquidez"), só que medida no preço de carta solta. Quem compra slab precisa
# da régua no preço do slab: as faixas abaixo são as raw multiplicadas por 3,
# fator calibrado no múltiplo PSA 10/raw OBSERVADO no top 25 deste repo em
# 2026-09-01 (mediana 3.3×, p25 2.5×, p75 5.4×, n=25) — não é chute, mas
# também não é previsão: é a mesma heurística de triagem, reancorada.
PSA10_PRICE_BANDS_USD = (15.0, 45.0, 120.0, 360.0, 900.0)

# Liquidez mínima (vendas/mês do PSA 10) para o componente valer cheio. Abaixo
# disso o slab é ilíquido e o preço de tabela não é preço realizável, então o
# componente é TETADO — mesma mecânica do teto de reprint forte no Supply.
# Corte 3.0/mês = fronteira dos tiers B/C da régua de liquidez da frota
# (`ebay-arbitrage-scanner/src/scorer.py::liquidity_tier`: A≥10, B≥3, C≥1).
PSA10_MIN_SALES_PER_MONTH = 3.0
PSA10_ILLIQUID_CAP = 12


def price_points_psa10(psa10_usd: float,
                       sales_per_month: float | None = None) -> int:
    """Componente de Preço (0-25) medido no PSA 10, com teto de iliquidez.

    `sales_per_month=None` (o PriceCharting não publicou volume) NÃO teta: sem
    dado é sem dado, não é sinal de iliquidez — a carta fica com a nota da
    faixa e a ausência é reportada na coluna de liquidez.
    """
    lo15, lo45, lo120, lo360, lo900 = PSA10_PRICE_BANDS_USD
    if psa10_usd < lo15:
        pts = 5
    elif psa10_usd < lo45:
        pts = 12
    elif psa10_usd < lo120:
        pts = 20
    elif psa10_usd < lo360:
        pts = 25
    elif psa10_usd < lo900:
        pts = 18
    else:
        pts = 12
    if sales_per_month is not None and sales_per_month < PSA10_MIN_SALES_PER_MONTH:
        return min(pts, PSA10_ILLIQUID_CAP)
    return pts


# ── Modo low pop (escassez + demanda medidas, não presumidas) ────────────────
# Decisão do operador (2026-09-21): a régua de longo prazo pra quem só compra
# PSA 10 troca os dois componentes CEGOS por dois MEDIDOS na própria página
# do PriceCharting (aba POP Report + vendas por nota):
#   Supply (idade do set)  →  ESCASSEZ  = quantas PSA 10 existem no censo;
#   Preço  (faixa)         →  DEMANDA   = vendas/mês da PSA 10.
# Personagem e Raridade continuam. Score segue 4×25 = 100.
#
# Faixas CALIBRADAS em 2026-09-21 sobre o pool medido do run canônico
# (--eras all --max-price 600 --graded-pool 300: 720 consultas, 300 slabs no
# teto, 224 com censo confiável). `python -m outlook.lowpop_calibration`
# reproduz a conta sobre qualquer run. Escala log: a diferença que importa é
# ordem de grandeza. Fatia do pool por faixa: 17% · 11% · 21% · 21% · 18% · 11%
# (nas faixas provisórias, 50-200 tinha 3% do pool e 2000-10000 concentrava 39%).
SCARCITY_POP10_BANDS = ((50, 25), (500, 22), (2000, 18), (5000, 12), (10000, 7))
SCARCITY_FLOOR = 3
# Vendas/mês chegam DISCRETIZADAS pelo PriceCharting ("N sales per day/week/
# month/year": 1/dia = 30, 1/semana = 4,3, 1/ano = 0,1) — por isso os cortes
# ficam ENTRE níveis. ≥60 = 2+/dia (12% do pool) · 30 = 1/dia (33%) · 5-29 =
# 1-3/semana (21%) · 2-4 = 2 a 8/mês (16%) · <2 (19%). A faixa provisória ≥30
# juntava 45% do pool num único degrau.
DEMAND_SALES_BANDS = ((60.0, 25), (30.0, 20), (5.0, 14), (2.0, 8))
DEMAND_FLOOR = 3

# Guards de página fina/errada (achado da sonda: o PriceCharting tem páginas
# duplicadas com censo quase vazio — Venusaur 15 com pop 4, Gardevoir ex 233
# com pop 2). Pop baixa ALI é página errada, não escassez; sem o guard viraria
# o topo do ranking. Regras:
#   - censo total abaixo de POP_TOTAL_MIN_TRUST → "pop não confiável";
#   - vendas/mês de PSA 10 MAIORES que o nº de PSA 10 existentes → impossível
#     (vende mais do que existe) → "pop não confiável".
POP_TOTAL_MIN_TRUST = 25

# Prêmio PSA 10 sobre a crua abaixo disto = o mercado não paga pela nota
# (informativo: vira nota na linha; NÃO entra no score até calibrar).
PSA10_PREMIUM_LOW = 1.5


def scarcity_points(pop_psa10: int) -> int:
    for cap, pts in SCARCITY_POP10_BANDS:
        if pop_psa10 <= cap:
            return pts
    return SCARCITY_FLOOR


def demand_points(sales_per_month: float) -> int:
    for floor, pts in DEMAND_SALES_BANDS:
        if sales_per_month >= floor:
            return pts
    return DEMAND_FLOOR


def pop_trust_issue(pop_psa: list[int] | None,
                    sales_per_month: float | None) -> str | None:
    """Motivo pra NÃO confiar no censo desta página, ou None se confiável."""
    if pop_psa is None:
        return "pop n/d"
    total = sum(pop_psa)
    if total < POP_TOTAL_MIN_TRUST:
        return f"pop não confiável (censo total {total} — página fina/duplicada)"
    p10 = pop_psa[9]
    if sales_per_month is not None and sales_per_month > p10:
        return (f"pop não confiável ({sales_per_month:g} vendas/mês de PSA 10 "
                f"com só {p10} no censo)")
    return None


@dataclass
class ScoredCard:
    card_id: str
    name: str
    set_name: str
    set_id: str
    number: str
    rarity: str
    series: str
    release: date
    market_usd: float
    notorious: str | None = None
    heavy_reprint: bool = False
    pts_character: int = 0
    pts_rarity: int = 0
    pts_supply: int = 0
    pts_price: int = 0
    tcg_url: str = ""
    low_usd: float | None = None  # menor anúncio TCGPlayer (condição NÃO filtrada; usado pelo run_availability)
    trend: str = ""           # preenchido (opcional) pelo módulo pricecharting
    # Modo graded (--graded): preço e liquidez do slab PSA 10 (módulo psa10).
    # Quando psa10_usd está preenchido, pts_price foi medido NELE, não no raw.
    psa10_usd: float | None = None
    psa10_sales_per_month: float | None = None
    psa10_status: str = ""
    dh_score: int | None = None  # 2ª opinião Double Holo (módulo doubleholo); NÃO entra no score
    # Modo low pop (--lowpop): escassez e demanda MEDIDAS (ver apply_lowpop).
    lowpop: bool = False
    pop_psa: list[int] | None = None      # censo PSA por nota (1..10)
    pop_cgc: list[int] | None = None
    raw_pc_usd: float | None = None       # "Ungraded" do PriceCharting (base do prêmio)
    tcg_product_id: str | None = None     # id TCGPlayer lido do PriceCharting (join)
    pts_scarcity: int = 0                 # substitui Supply no modo low pop
    pts_demand: int = 0                   # substitui Preço no modo low pop
    pop_issue: str | None = None          # motivo do censo não valer (None = confiável)
    notes: list[str] = field(default_factory=list)

    @property
    def score(self) -> int:
        if self.lowpop:
            return (self.pts_character + self.pts_rarity
                    + self.pts_scarcity + self.pts_demand)
        return self.pts_character + self.pts_rarity + self.pts_supply + self.pts_price

    @property
    def pop_psa10(self) -> int | None:
        return self.pop_psa[9] if self.pop_psa else None

    @property
    def pop_total(self) -> int | None:
        return sum(self.pop_psa) if self.pop_psa else None

    @property
    def gem_rate(self) -> float | None:
        """PSA 10 / total gradado PSA (0-1). None sem censo ou censo vazio."""
        tot = self.pop_total
        if not tot:
            return None
        return self.pop_psa[9] / tot

    @property
    def psa10_premium(self) -> float | None:
        """Preço PSA 10 / preço da carta crua (PriceCharting). None sem os dois."""
        if self.psa10_usd is None or not self.raw_pc_usd:
            return None
        return self.psa10_usd / self.raw_pc_usd

    @property
    def age_months(self) -> int:
        t = date.today()
        return (t.year - self.release.year) * 12 + (t.month - self.release.month)


def apply_psa10(sc, psa10_usd: float | None,
                sales_per_month: float | None = None,
                status: str = "") -> None:
    """Aplica o modo graded numa carta já pontuada, IN-PLACE.

    Existe como função à parte porque o preço PSA 10 chega DEPOIS da triagem:
    o ranking raw define o pool a consultar (não dá pra consultar o catálogo
    inteiro carta a carta), e só então o componente de Preço é remedido no
    slab. Sem preço PSA 10, o componente permanece o raw e a linha ganha nota
    explicando por quê — nunca zeramos nem inventamos.
    """
    sc.psa10_usd = psa10_usd
    sc.psa10_sales_per_month = sales_per_month
    sc.psa10_status = status
    if psa10_usd is None:
        if status and status != "ok":
            sc.notes.append(f"sem preço PSA 10 ({status}) — "
                            "Preço medido na régua raw")
        return
    sc.pts_price = price_points_psa10(psa10_usd, sales_per_month)
    if (sales_per_month is not None
            and sales_per_month < PSA10_MIN_SALES_PER_MONTH):
        sc.notes.append(
            f"PSA 10 ilíquido ({sales_per_month:g} vendas/mês) — preço de "
            "tabela pode não ser realizável")


def apply_lowpop(sc, r: dict) -> None:
    """Aplica o modo low pop numa carta já pontuada, IN-PLACE, a partir do
    dict de `psa10.fetch_psa10` (uma página = preço PSA 10 + vendas + censo).

    Ordem: primeiro o graded (preço/liquidez no slab, com as notas de sempre),
    depois os dois componentes medidos:
      - ESCASSEZ: pop de PSA 10 no censo → `scarcity_points`. Censo ausente ou
        não confiável (guards) → cai na régua de Supply por idade, com nota.
      - DEMANDA: vendas/mês da PSA 10 → `demand_points`. Sem volume publicado
        → cai no componente de Preço já remedido no slab (ou raw), com nota.
    Nunca zera, nunca inventa: toda queda de régua é declarada na linha.
    """
    apply_psa10(sc, r.get("usd"), r.get("sales_per_month"), r.get("status", ""))
    sc.lowpop = True
    sc.pop_psa = r.get("pop_psa")
    sc.pop_cgc = r.get("pop_cgc")
    sc.raw_pc_usd = r.get("raw_usd")
    sc.tcg_product_id = r.get("tcg_product_id")
    spm = r.get("sales_per_month")

    issue = pop_trust_issue(sc.pop_psa, spm)
    sc.pop_issue = issue
    if issue is None:
        sc.pts_scarcity = scarcity_points(sc.pop_psa[9])
    else:
        sc.pts_scarcity = sc.pts_supply
        sc.notes.append(f"{issue} — Escassez medida por idade do set")

    if spm is not None:
        sc.pts_demand = demand_points(spm)
    else:
        sc.pts_demand = sc.pts_price
        sc.notes.append("vendas/mês n/d — Demanda medida pela faixa de preço")

    prem = sc.psa10_premium
    if prem is not None and prem < PSA10_PREMIUM_LOW:
        sc.notes.append(f"prêmio PSA 10 baixo ({prem:.1f}× a crua)")


def lowpop_pool(cards: list, pool_n: int) -> list:
    """Quem consultar no PriceCharting no modo low pop — round-robin por era.

    Por que não "top-N pelo score cru": o score cru carrega justamente os dois
    componentes que este modo substitui (Supply por idade, Preço por faixa), e
    a Raridade é cega a era (o "Holo Rare" de 1999 vale 3 pontos, o SIR de
    2025 vale 25) — um pool por score cru sai 100% SV e o vintage nunca é
    medido (visto no smoke de 2026-09-21: 24/24 cartas do pool eram SV). Aqui
    cada era contribui em rodízio com as suas melhores cartas por Personagem +
    Raridade (desempate: preço de mercado, proxy de demanda até medir), até
    fechar o pool. Era com menos cartas que a cota cede a vaga às outras.
    """
    by_series: dict[str, list] = {}
    for c in cards:
        by_series.setdefault(c.series, []).append(c)
    queues = [sorted(cs, key=lambda c: (-(c.pts_character + c.pts_rarity),
                                       -c.market_usd))
              for _, cs in sorted(by_series.items())]
    pool: list = []
    idx = 0
    while len(pool) < pool_n and any(queues):
        q = queues[idx % len(queues)]
        if q:
            pool.append(q.pop(0))
        idx += 1
        if idx % len(queues) == 0:
            queues = [q for q in queues if q]
            if not queues:
                break
    return pool


def score_card(card: dict, set_meta: dict, market_usd: float,
               today: date | None = None,
               psa10_usd: float | None = None,
               psa10_sales_per_month: float | None = None,
               psa10_status: str = "") -> ScoredCard:
    today = today or date.today()
    release = date.fromisoformat(set_meta["releaseDate"].replace("/", "-"))
    heavy = is_heavy_reprint(set_meta["id"], set_meta.get("name", ""))
    hit = match_notorious(card.get("name", ""))
    sc = ScoredCard(
        card_id=card.get("id", ""),
        name=card.get("name", ""),
        set_name=set_meta.get("name", ""),
        set_id=set_meta.get("id", ""),
        number=card.get("number", ""),
        rarity=card.get("rarity", "") or "?",
        series=set_meta.get("series", ""),
        release=release,
        market_usd=market_usd,
        notorious=hit,
        heavy_reprint=heavy,
    )
    sc.pts_character = tier_points(hit)
    sc.pts_rarity = rarity_points(sc.rarity)
    # TCGPlayer marca alt-arts no NOME ("... (Alternate Art Secret)") — é o
    # tier que historicamente mais valoriza; promove ao máximo do componente.
    if "alternate" in sc.name.lower():
        sc.pts_rarity = 25
        sc.notes.append("alt-art (detectada pelo nome TCGPlayer)")
    sc.pts_supply = supply_points(release, today, heavy)
    sc.pts_price = price_points(market_usd)
    if psa10_usd is not None or psa10_status:
        apply_psa10(sc, psa10_usd, psa10_sales_per_month, psa10_status)
    if heavy:
        sc.notes.append("reprint forte — supply não encolhe como o normal")
    if (sc.series == "Sword & Shield" and sc.pts_rarity in (12, 14)
            and "alternate" not in sc.name.lower()):
        sc.notes.append("era SWSH: alt-art não distinguível pela raridade da API")
    return sc
