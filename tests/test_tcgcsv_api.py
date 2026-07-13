"""Testes das funções puras da fonte tcgcsv (sem rede)."""
from outlook.tcgcsv_api import _best_prices_by_pid, _strip_number_suffix


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


def test_best_prices_picks_variant_with_highest_market_and_its_low():
    prices = [
        {"productId": 1, "subTypeName": "Normal",
         "marketPrice": 10.0, "lowPrice": 8.0},
        {"productId": 1, "subTypeName": "Holofoil",
         "marketPrice": 40.0, "lowPrice": 33.5},
        # reverse nunca entra (mesma regra do market de sempre)
        {"productId": 1, "subTypeName": "Reverse Holofoil",
         "marketPrice": 99.0, "lowPrice": 1.0},
    ]
    assert _best_prices_by_pid(prices) == {1: (40.0, 33.5)}


def test_best_prices_low_invalid_stays_none_and_market_zero_is_skipped():
    prices = [
        {"productId": 2, "subTypeName": "Holofoil",
         "marketPrice": 25.0, "lowPrice": None},
        {"productId": 3, "subTypeName": "Holofoil",
         "marketPrice": 0, "lowPrice": 5.0},          # market inválido: fora
        {"productId": 4, "subTypeName": "Holofoil",
         "marketPrice": 12.0},                        # sem lowPrice na fonte
    ]
    out = _best_prices_by_pid(prices)
    assert out == {2: (25.0, None), 4: (12.0, None)}
