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
    "Shining Fates", "Crown Zenith", "Celebrations",
)


def is_heavy_reprint(set_id: str, set_name: str) -> bool:
    return (set_id in HEAVY_REPRINT_SET_IDS
            or any(part in set_name for part in HEAVY_REPRINT_NAME_PARTS))


def rarity_points(rarity: str) -> int:
    """Pesos por grupo de raridade (match por substring, nomes variam por era)."""
    r = (rarity or "").lower()
    if "special illustration" in r:
        return 25
    if "illustration" in r:
        return 20
    if "trainer gallery" in r or "character" in r:
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
    trend: str = ""           # preenchido (opcional) pelo módulo pricecharting
    notes: list[str] = field(default_factory=list)

    @property
    def score(self) -> int:
        return self.pts_character + self.pts_rarity + self.pts_supply + self.pts_price

    @property
    def age_months(self) -> int:
        t = date.today()
        return (t.year - self.release.year) * 12 + (t.month - self.release.month)


def score_card(card: dict, set_meta: dict, market_usd: float,
               today: date | None = None) -> ScoredCard:
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
    if heavy:
        sc.notes.append("reprint forte — supply não encolhe como o normal")
    if (sc.series == "Sword & Shield" and sc.pts_rarity in (12, 14)
            and "alternate" not in sc.name.lower()):
        sc.notes.append("era SWSH: alt-art não distinguível pela raridade da API")
    return sc
