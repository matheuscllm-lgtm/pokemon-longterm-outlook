"""Lista curada de personagens "notórios" (Pokémon + treinadores) + matcher.

"Notório" aqui = personagem-ícone com histórico consistente de DEMANDA no
mercado colecionável (não é previsão de preço — é um flag de triagem). Cada
personagem entra num TIER DE APELO, que vira a pontuação do componente
"Personagem" do score:

    S = ícone de liquidez (lidera demanda em quase toda era)   -> 25
    A = fan-favorite forte (demanda perene consistente)        -> 18
    B = demanda sólida de segunda onda                         -> 12
    (fora da lista)                                            ->  8

Por que treinadores entram (era a maior lacuna do score): SIR/full-art de
treinador popular — sobretudo as "treinadoras" (Marnie, Lillie, Cynthia, Iono,
Acerola) — historicamente valorizam TANTO OU MAIS que SIR de Pokémon do mesmo
set, por dois motivos estruturais: (1) há MENOS SIR de treinador por set que de
Pokémon (escassez dentro do set) e (2) a demanda soma colecionador de
personagem + de arte + quem fecha o set. Apelo é apelo: a mesma escala de tier
vale pra monstro e pra humano. O componente antigo era binário (25 p/ Pokémon
notório, 8 pro resto) — treinador nenhum casava e o degrau não tinha meio-termo.

A lista é curada à mão e ajustável (mover um nome de tier = trocá-lo de tupla).
O operador decide capital; o flag/tier só ordena o que olhar primeiro.

Regras do matcher (veja tests/test_notorious.py):
- Match por PALAVRA INTEIRA dentro do nome da carta, case-insensitive.
  "Charizard ex", "Dark Charizard", "Mega Charizard EX" -> casam "Charizard".
  "Charizardite X" (a Mega Stone, item) -> NÃO casa (a palavra é "Charizardite").
- "Mew" não casa dentro de "Mewtwo" (lookahead); "Mewtwo" tem entrada própria.
- Quando dois notórios casam na mesma carta, vence o de MAIOR tier de apelo
  (empate -> match mais longo): "N's Zoroark ex" -> "N" (tier S) acima de
  "Zoroark" (tier B); "Cynthia's Garchomp ex" -> "Cynthia". A ideia: o
  personagem de maior apelo é o que puxa o valor da carta. "Iono's Bellibolt
  ex" -> "Iono" (Bellibolt nem é notório).
- "N" (treinador) só casa como token isolado ("N", "N's Zoroark") — nunca
  dentro de "Snorlax"/"Nessa" (o lookahead exige que NÃO venha letra depois).
"""
from __future__ import annotations

import re
import unicodedata

# ── Pontos por tier de apelo ─────────────────────────────────────────────────
S_POINTS, A_POINTS, B_POINTS, APPEAL_DEFAULT = 25, 18, 12, 8

# ── Pokémon por tier ─────────────────────────────────────────────────────────
POKEMON_S: tuple[str, ...] = (
    # Ícones absolutos de liquidez — lideram demanda em qualquer era.
    # Charizard é historicamente a carta mais líquida do hobby; Umbreon domina
    # as alt-arts modernas (Moonbreon); Eevee é o hub do fandom eeveelution.
    "Charizard", "Pikachu", "Umbreon", "Eevee", "Mewtwo", "Mew",
    "Rayquaza", "Lugia", "Gengar", "Gardevoir",
)
POKEMON_A: tuple[str, ...] = (
    # Starters de Kanto (formas mais queridas) + demais eeveelutions + ícones
    # modernos/competitivos + fan-favorites Gen 1 de liquidez alta. Demanda
    # perene, só não no patamar absoluto do tier S.
    "Charmander", "Blastoise", "Squirtle", "Venusaur", "Bulbasaur",
    "Vaporeon", "Jolteon", "Flareon", "Espeon", "Leafeon", "Glaceon", "Sylveon",
    "Lucario", "Greninja", "Dragapult", "Mimikyu",
    "Snorlax", "Dragonite", "Gyarados", "Tyranitar", "Giratina", "Darkrai",
)
POKEMON_B: tuple[str, ...] = (
    # Evoluções intermediárias, aves lendárias, lendários/míticos e
    # pseudo-lendários de segunda onda — demanda sólida, menos perene que A.
    "Charmeleon", "Wartortle", "Ivysaur", "Raichu",
    "Articuno", "Zapdos", "Moltres", "Ho-Oh", "Celebi",
    "Kyogre", "Groudon", "Latias", "Latios", "Jirachi", "Dialga", "Palkia",
    "Arceus", "Garchomp", "Metagross", "Salamence", "Goodra",
    "Alakazam", "Machamp", "Arcanine", "Lapras", "Ditto", "Absol", "Zoroark",
)

# ── Treinadores por tier (a lacuna que esta mudança fecha) ───────────────────
TRAINER_S: tuple[str, ...] = (
    # Blue-chips de treinador com valorização comprovada — as "treinadoras"
    # que puxam chase (Marnie/Lillie/Cynthia/Iono) + Acerola (SAR entre as
    # cartas modernas mais caras) + N (culto próprio; N's ... sempre procurado).
    "Marnie", "Lillie", "Cynthia", "Iono", "Acerola", "N",
)
TRAINER_A: tuple[str, ...] = (
    # Treinadores de forte apelo recorrente (full-art/SIR sempre procurados).
    "Nessa", "Bea", "Sonia", "Klara", "Serena", "Misty", "Erika", "Sabrina",
    "Skyla", "Volo", "Giovanni", "Penny", "Nemona", "Arven", "Hilda", "Rosa",
)

# ── Mapa nome -> pontos (sem colisões; cada nome em exatamente um tier) ───────
_TIER_GROUPS: tuple[tuple[tuple[str, ...], int], ...] = (
    (POKEMON_S, S_POINTS), (TRAINER_S, S_POINTS),
    (POKEMON_A, A_POINTS), (TRAINER_A, A_POINTS),
    (POKEMON_B, B_POINTS),
)
_POINTS: dict[str, int] = {
    name: pts for names, pts in _TIER_GROUPS for name in names
}

# Listas achatadas (compat + introspecção). NOTORIOUS_POKEMON é mantido pra
# quem só quer os Pokémon; NOTORIOUS cobre tudo (Pokémon + treinadores).
NOTORIOUS_POKEMON: tuple[str, ...] = POKEMON_S + POKEMON_A + POKEMON_B
NOTORIOUS: tuple[str, ...] = tuple(_POINTS.keys())

# Pré-compila um padrão por nome: palavra inteira, case-insensitive.
# \b não basta sozinho p/ acentos, então normalizamos o texto antes (NFD).
_PATTERNS: dict[str, re.Pattern[str]] = {
    name: re.compile(rf"(?<![A-Za-z]){re.escape(name)}(?![a-z])", re.IGNORECASE)
    for name in _POINTS
}


def _normalize(text: str) -> str:
    """Remove acentos p/ matching robusto (ex.: 'Pokémon' -> 'Pokemon')."""
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def match_notorious(card_name: str | None) -> str | None:
    """Retorna o nome do personagem notório contido no nome da carta, ou None.

    "Charizard ex" -> "Charizard"; "Charizardite X" -> None; "Mega Gengar ex"
    -> "Gengar"; "Mewtwo VSTAR" -> "Mewtwo" (não "Mew"); "Marnie" -> "Marnie";
    "N's Zoroark ex" -> "N".
    """
    if not card_name:
        return None
    text = _normalize(str(card_name))
    best: str | None = None
    for name, pattern in _PATTERNS.items():
        if pattern.search(text):
            # Maior tier de apelo vence; empate -> match mais longo.
            # ("N's Zoroark ex" -> N (S) acima de Zoroark (B); Mewtwo > Mew.)
            if best is None or (_POINTS[name], len(name)) > (_POINTS[best], len(best)):
                best = name
    return best


def tier_points(notorious_name: str | None) -> int:
    """Pontos do tier de um nome JÁ casado por match_notorious (None -> 8)."""
    return _POINTS.get(notorious_name, APPEAL_DEFAULT)


def appeal_points(card_name: str | None) -> int:
    """Pontos do componente Personagem (0-25) pelo tier de apelo do match.

    Conveniência: faz match + lookup de tier a partir do nome bruto da carta.
    S=25, A=18, B=12; sem match notório -> APPEAL_DEFAULT (8).
    """
    return tier_points(match_notorious(card_name))


def is_notorious(card_name: str | None) -> bool:
    return match_notorious(card_name) is not None
