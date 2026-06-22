"""Testes do matcher de Pokémon notórios — palavra inteira, acentos, limites.

Estes casos são citados na docstring do `outlook/notorious.py` como contrato
do matcher; aqui eles ficam executáveis. Cobrem o que de fato pega gente de
surpresa: itens com o nome embutido (Charizardite), prefixo que não pode casar
(Mew dentro de Mewtwo), nomes com hífen (Ho-Oh) e o sufixo de número que o
TCGPlayer cola em alguns nomes.
"""
from outlook.notorious import (NOTORIOUS_POKEMON, is_notorious,
                               match_notorious)


def test_basic_forms_match_the_pokemon():
    assert match_notorious("Charizard ex") == "Charizard"
    assert match_notorious("Dark Charizard") == "Charizard"
    assert match_notorious("Mega Lucario ex") == "Lucario"
    assert match_notorious("Gardevoir ex") == "Gardevoir"


def test_match_ignores_tcgplayer_number_suffix():
    # Mesmo com o ' - 181/132' que o tcgcsv às vezes traz, o nome casa.
    assert match_notorious("Mega Latias ex - 181/132") == "Latias"
    assert match_notorious("N's Zoroark ex - 286/217") == "Zoroark"


def test_item_with_embedded_name_does_not_match():
    # "Charizardite X" é a Mega Stone (item); a palavra é "Charizardite",
    # não "Charizard" — o lookahead (?![a-z]) impede o match.
    assert match_notorious("Charizardite X") is None


def test_whole_word_only_mew_not_inside_mewtwo():
    # "Mew" NÃO pode casar dentro de "Mewtwo"; "Mewtwo" tem entrada própria.
    assert match_notorious("Mewtwo VSTAR") == "Mewtwo"
    assert match_notorious("Team Rocket's Mewtwo ex") == "Mewtwo"
    # Mas "Mew" sozinho casa.
    assert match_notorious("Mew ex") == "Mew"


def test_hyphenated_name_matches():
    assert match_notorious("Ho-Oh ex") == "Ho-Oh"


def test_accents_in_surrounding_text_do_not_break_match():
    # O texto é normalizado (NFD) antes do match — acento adjacente não atrapalha.
    assert match_notorious("Pokémon Pikachu δ") == "Pikachu"


def test_non_notorious_and_empty_return_none():
    assert match_notorious("Tinkatuff") is None
    assert match_notorious("Iron Valiant ex") is None
    assert match_notorious("") is None
    assert match_notorious(None) is None


def test_is_notorious_is_boolean_wrapper():
    assert is_notorious("Pikachu") is True
    assert is_notorious("Tinkatuff") is False


def test_curated_list_has_no_duplicates():
    # Lista curada à mão — uma duplicata silenciosa passaria despercebida.
    assert len(NOTORIOUS_POKEMON) == len(set(NOTORIOUS_POKEMON))
