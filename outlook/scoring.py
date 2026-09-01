"""Score de potencial de LONGO PRAZO (0-100) por carta — heurística declarada.

O score soma 4 componentes de 0-25, cada um com racional explícito (a tabela
final mostra o racional por linha). NÃO é previsão de preço nem conselho de
investimento: é uma triagem ordenável pra ajudar o operador a olhar primeiro
o que tem mais características historicamente associadas a valorização.
Quem decide capital é o operador.

Componentes:
  1. PERSONAGEM  (0-25) — Pokémon notório (lista curada) tem demanda perene.
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

from .notorious import match_notorious

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
    notes: list[str] = field(default_factory=list)

    @property
    def score(self) -> int:
        return self.pts_character + self.pts_rarity + self.pts_supply + self.pts_price

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
    sc.pts_character = 25 if hit else 8
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
