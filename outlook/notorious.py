"""Lista curada de Pokémon "notórios" + matcher de nome de carta.

"Notório" aqui = Pokémon-ícone com histórico consistente de demanda no mercado
colecionável (não é previsão de preço — é um flag de triagem). A lista é curada
à mão, em grupos comentados com o porquê. O operador decide capital; o flag só
destaca a linha na tabela.

Regras do matcher (importante — veja os testes em tests/test_notorious.py):
- Match por PALAVRA INTEIRA dentro do nome da carta, case-insensitive.
  "Charizard ex", "Dark Charizard", "Mega Charizard EX" → casam "Charizard".
  "Charizardite X" (a Mega Stone, item) → NÃO casa (a palavra é "Charizardite",
  não "Charizard").
- "Mew" não casa dentro de "Mewtwo" (palavra inteira), mas "Mewtwo" tem entrada
  própria na lista.
"""
from __future__ import annotations

import re
import unicodedata

# ── Lista curada (~55 nomes), em grupos com racional ─────────────────────────
NOTORIOUS_POKEMON: tuple[str, ...] = (
    # Kanto starters + evoluções finais — os ícones absolutos do colecionismo;
    # Charizard é historicamente a carta mais líquida do hobby.
    "Charizard", "Charmander", "Charmeleon",
    "Blastoise", "Squirtle", "Wartortle",
    "Venusaur", "Bulbasaur", "Ivysaur",
    # Pikachu-line — mascote da franquia; Pikachu promo/alt-art tem demanda
    # perene; Raichu pega carona.
    "Pikachu", "Raichu",
    # Eevee + TODAS as eeveelutions — fandom dedicado ("Eeveelution collectors");
    # Umbreon em particular domina alt-arts modernas (Moonbreon).
    "Eevee", "Vaporeon", "Jolteon", "Flareon",
    "Espeon", "Umbreon", "Leafeon", "Glaceon", "Sylveon",
    # Lendários/míticos Gen 1-2 — vintage premium e reprints sempre procurados.
    "Mewtwo", "Mew", "Lugia", "Ho-Oh", "Celebi",
    "Articuno", "Zapdos", "Moltres",
    # Pseudo-lendários e "fan favorites" Gen 1 — liquidez alta em qualquer era.
    "Dragonite", "Gyarados", "Snorlax", "Gengar", "Alakazam", "Machamp",
    "Arcanine", "Lapras", "Ditto",
    # Gen 3+ lendários com base de fãs forte — Rayquaza alt-art é chase clássico.
    "Rayquaza", "Kyogre", "Groudon", "Latias", "Latios", "Jirachi",
    "Metagross", "Salamence",
    # Pseudo-lendários e ícones Gen 4-6 — Garchomp/Lucario têm presença
    # competitiva + colecionável; Giratina/Darkrai puxam alt-arts caras.
    "Garchomp", "Lucario", "Giratina", "Darkrai", "Dialga", "Palkia",
    "Arceus", "Greninja", "Goodra", "Dragapult",
    # Modernos com culto próprio — Mimikyu/Gardevoir lideram demanda recente;
    # Tyranitar é chase desde Neo.
    "Mimikyu", "Gardevoir", "Tyranitar", "Absol", "Zoroark",
)

# Pré-compila um padrão por nome: palavra inteira, case-insensitive.
# \b não basta sozinho p/ acentos, então normalizamos o texto antes (NFD).
_PATTERNS: dict[str, re.Pattern[str]] = {
    name: re.compile(rf"(?<![A-Za-z]){re.escape(name)}(?![a-z])", re.IGNORECASE)
    for name in NOTORIOUS_POKEMON
}


def _normalize(text: str) -> str:
    """Remove acentos p/ matching robusto (ex.: 'Pokémon' → 'Pokemon')."""
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def match_notorious(card_name: str | None) -> str | None:
    """Retorna o nome do Pokémon notório contido no nome da carta, ou None.

    "Charizard ex" → "Charizard"; "Charizardite X" → None; "Mega Gengar ex"
    → "Gengar"; "Mewtwo VSTAR" → "Mewtwo" (não "Mew").
    """
    if not card_name:
        return None
    text = _normalize(str(card_name))
    best: str | None = None
    for name, pattern in _PATTERNS.items():
        if pattern.search(text):
            # Prefere o match mais longo (Mewtwo > Mew se ambos casassem).
            if best is None or len(name) > len(best):
                best = name
    return best


def is_notorious(card_name: str | None) -> bool:
    return match_notorious(card_name) is not None
