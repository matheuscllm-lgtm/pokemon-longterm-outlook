"""Score de potencial de LONGO PRAZO para produto SELADO (0-100).

Os singles têm scoring.py; selado tem dinâmica própria (e até mais limpa: a
oferta é o produto físico, sem variação de raridade). Mesma filosofia — 4
componentes de 0-25 com racional aberto. NÃO é previsão nem conselho.

Ciclo de vida do selado: (a) prêmio de lançamento → (b) compressão enquanto a
fábrica imprime → (c) valorização real só DEPOIS de sair de impressão (OOP).
Os componentes tentam localizar o produto nesse ciclo:

  1. TIPO        (0-25) — liquidez/colecionabilidade do SKU (ETB/Box > Bundle > Tin).
  2. IDADE       (0-25) — meses desde o lançamento: oferta no varejo vai secando.
  3. MSRP        (0-25) — múltiplo sobre o preço de etiqueta: perto do MSRP =
                          espaço pra crescer; já a 3-4x = prêmio de lançamento
                          (precificado), pouco espaço.
  4. REIMPRESSÃO (0-25) — set normal (sai de catálogo) = oferta encolhe = 25;
                          set ESPECIAL impresso em massa por anos = 6.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .scoring import is_heavy_reprint, supply_points

# Peso de colecionabilidade/liquidez por tipo de SKU.
TYPE_POINTS = {
    "Booster Box": 25, "Elite Trainer Box": 25, "Booster Bundle": 18,
    "Collection": 14, "Mini Tin": 13, "Tin": 13, "Build & Battle": 12,
    "Booster Pack": 8,
}
# MSRP de etiqueta aproximado (US$) por tipo — base do múltiplo. É aproximação
# pública; o componente usa faixas largas, então pequenos erros não viram nota.
MSRP = {
    "Booster Box": 160.0, "Elite Trainer Box": 60.0, "Booster Bundle": 27.0,
    "Collection": 25.0, "Mini Tin": 15.0, "Tin": 25.0, "Build & Battle": 25.0,
    "Booster Pack": 5.0,
}


def type_points(ptype: str) -> int:
    return TYPE_POINTS.get(ptype, 8)


def msrp_points(ptype: str, market_usd: float) -> int:
    msrp = MSRP.get(ptype)
    if not msrp or market_usd <= 0:
        return 12  # neutro quando não sabemos o MSRP do tipo
    mult = market_usd / msrp
    if mult < 1.2:
        return 25  # no/abaixo do varejo: espaço máximo
    if mult < 1.8:
        return 22
    if mult < 2.5:
        return 16
    if mult < 4.0:
        return 10
    return 5       # >4x MSRP: prêmio de lançamento, já precificado


def reprint_points(heavy: bool) -> int:
    return 6 if heavy else 25


@dataclass
class ScoredSealed:
    product_id: str
    name: str
    product_type: str
    set_name: str
    set_id: str
    series: str
    release: date
    market_usd: float
    heavy_reprint: bool = False
    pts_type: int = 0
    pts_age: int = 0
    pts_msrp: int = 0
    pts_reprint: int = 0
    tcg_url: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def score(self) -> int:
        return self.pts_type + self.pts_age + self.pts_msrp + self.pts_reprint

    @property
    def msrp_multiple(self) -> float | None:
        m = MSRP.get(self.product_type)
        return (self.market_usd / m) if m else None

    @property
    def age_months(self) -> int:
        t = date.today()
        return (t.year - self.release.year) * 12 + (t.month - self.release.month)


def score_sealed(prod: dict, set_meta: dict, market_usd: float,
                 today: date | None = None) -> ScoredSealed:
    today = today or date.today()
    release = date.fromisoformat(set_meta["releaseDate"].replace("/", "-"))
    heavy = is_heavy_reprint(set_meta["id"], set_meta.get("name", ""))
    ptype = prod.get("product_type", "?")
    sc = ScoredSealed(
        product_id=prod.get("id", ""), name=prod.get("name", ""),
        product_type=ptype, set_name=set_meta.get("name", ""),
        set_id=set_meta.get("id", ""), series=set_meta.get("series", ""),
        release=release, market_usd=market_usd, heavy_reprint=heavy,
    )
    sc.pts_type = type_points(ptype)
    sc.pts_age = supply_points(release, today, heavy_reprint=False)  # idade pura
    sc.pts_msrp = msrp_points(ptype, market_usd)
    sc.pts_reprint = reprint_points(heavy)
    mult = sc.msrp_multiple
    if mult is not None:
        sc.notes.append(f"{mult:.1f}x MSRP")
    if heavy:
        sc.notes.append("set especial — oferta não encolhe (reimpressão)")
    return sc


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|")


def sealed_ranking_markdown(items: list[ScoredSealed], top_n: int) -> str:
    ranked = sorted(items, key=lambda c: (-c.score, -c.market_usd))[:top_n]
    lines = [f"## Top {len(ranked)} selados — score de longo prazo "
             f"(heurística 0-100; decisão é do operador)", "",
             "| # | Score | Produto | Tipo | Set | Preço US$ | ×MSRP | Idade | "
             "Tipo | Idade | MSRP | Reprint | Notas | Link |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, c in enumerate(ranked, 1):
        mult = c.msrp_multiple
        lines.append(
            f"| {i} | **{c.score}** | {_md_escape(c.name)} | {c.product_type} | "
            f"{_md_escape(c.set_name)} | {c.market_usd:.2f} | "
            f"{('%.1fx' % mult) if mult else '—'} | {c.age_months}m | "
            f"{c.pts_type} | {c.pts_age} | {c.pts_msrp} | {c.pts_reprint} | "
            f"{_md_escape('; '.join(c.notes))} | [TCG]({c.tcg_url}) |")
    lines.append("")
    lines.append("_Score selado = Tipo + Idade + MSRP + Reimpressão (0-25 cada). "
                 "Heurística de triagem com racional aberto — NÃO é previsão nem "
                 "conselho. Múltiplo sobre MSRP é aproximado. Lotes (case/display) "
                 "ficam fora de propósito: distorcem por serem múltiplas unidades._")
    return "\n".join(lines)
