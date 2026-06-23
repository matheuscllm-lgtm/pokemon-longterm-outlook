"""Testes do helper puro de nome de set (sem rede)."""
from outlook.sets import strip_era_prefix


def test_strips_numbered_era_prefix():
    assert strip_era_prefix("SWSH07: Evolving Skies") == "Evolving Skies"
    assert strip_era_prefix("SV03: Obsidian Flames") == "Obsidian Flames"
    assert strip_era_prefix("ME01: Mega Evolution") == "Mega Evolution"
    assert strip_era_prefix("SV: Scarlet & Violet 151") == "Scarlet & Violet 151"


def test_keeps_name_without_colon():
    assert strip_era_prefix("Pokemon GO") == "Pokemon GO"
    assert strip_era_prefix("Celebrations") == "Celebrations"


def test_does_not_strip_long_left_side():
    # Trecho antes do ':' com > 8 chars não é prefixo de era — não corta.
    assert (strip_era_prefix("Celebrations: Classic Collection")
            == "Celebrations: Classic Collection")


def test_empty_rest_keeps_original_not_empty_string():
    # "SV03:" sem nada depois NÃO pode virar "" (regressão do double-space).
    assert strip_era_prefix("SV03:") == "SV03:"
    assert strip_era_prefix("SV03:   ") == "SV03:   "


def test_preserves_case_and_accents():
    # Cru: não normaliza (quem quiser, faz por fora).
    assert strip_era_prefix("SV: Pokémon ABC") == "Pokémon ABC"
