"""Testes das funções puras da fonte tcgcsv (sem rede)."""
from outlook.tcgcsv_api import _best_market_by_pid, _strip_number_suffix


def test_strips_exact_number_suffix():
    # O TCGPlayer cola ' - 008/159' em alguns nomes; a coluna Nº já mostra isso.
    assert _strip_number_suffix("Maractus - 008/159", "008/159") == "Maractus"
    assert _strip_number_suffix("Gardevoir ex - 245/198", "245/198") == "Gardevoir ex"


def test_keeps_name_without_suffix():
    assert _strip_number_suffix("Caterpie", "001/159") == "Caterpie"
    assert _strip_number_suffix("Steven's Metagross ex", "289/172") == "Steven's Metagross ex"


def test_only_strips_when_suffix_matches_the_number():
    # Não corta um ' - algo' que não seja exatamente o número da carta.
    assert _strip_number_suffix("Mr. Mime - Gen 1", "122/078") == "Mr. Mime - Gen 1"


def test_preserves_alt_art_descriptor_before_number():
    # Descritor de alt-art (usado na detecção de raridade) é preservado.
    name = "Charizard ex (Alternate Art Secret) - 215/197"
    assert (_strip_number_suffix(name, "215/197")
            == "Charizard ex (Alternate Art Secret)")


def test_empty_number_is_noop():
    assert _strip_number_suffix("Pikachu", "") == "Pikachu"


def test_best_market_ignores_reverse_and_keeps_max_variant():
    # Regra única de preço (compartilhada por cartas e selados): ignora
    # "Reverse Holofoil" e fica com a variante de maior market por produto.
    prices = [
        {"productId": 1, "subTypeName": "Normal", "marketPrice": 10.0},
        {"productId": 1, "subTypeName": "Holofoil", "marketPrice": 25.5},
        {"productId": 1, "subTypeName": "Reverse Holofoil", "marketPrice": 99.0},
        {"productId": 2, "subTypeName": "Normal", "marketPrice": 0},      # sem preço
        {"productId": 3, "subTypeName": "Normal", "marketPrice": None},   # sem preço
        {"productId": 4, "subTypeName": None, "marketPrice": 3.0},        # subType ausente
    ]
    assert _best_market_by_pid(prices) == {1: 25.5, 4: 3.0}


def test_best_market_empty_input():
    assert _best_market_by_pid([]) == {}
