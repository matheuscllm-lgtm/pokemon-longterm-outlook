"""Testes do formato de entrega (report.ranking_markdown) — colunas e links.

Travam as três mudanças pedidas no modo de entrega: (1) número junto ao nome,
(2) colunas de componente fora da tabela, (3) coluna de link do PriceCharting.
"""
from datetime import date

from outlook.report import _pricecharting_search_url, ranking_markdown
from outlook.scoring import ScoredCard


def _card(**kw) -> ScoredCard:
    base = dict(
        card_id="x", name="Mew V (Alternate Full Art)",
        set_name="SWSH08: Fusion Strike", set_id="g", number="251",
        rarity="Ultra Rare", series="Sword & Shield",
        release=date(2021, 11, 12), market_usd=115.18,
        notorious="Mew", pts_character=25, pts_rarity=25,
        pts_supply=25, pts_price=25, tcg_url="https://tcg/x",
        trend="↑ +114% (1a)",
    )
    base.update(kw)
    return ScoredCard(**base)


def _header(md: str) -> str:
    return next(l for l in md.splitlines() if l.startswith("| # |"))


def test_card_name_carries_number():
    md = ranking_markdown([_card()], 10)
    assert "Mew V (Alternate Full Art) #251" in md


def test_component_columns_and_number_column_dropped_from_header():
    md = ranking_markdown([_card()], 10)
    header = _header(md)
    assert "Persngm" not in header          # componente Personagem saiu
    assert "Supply" not in header           # componente Supply saiu
    assert "Nº" not in header               # número foi pro nome
    assert "| Preço |" not in header        # componente Preço saiu...
    assert "Preço US$" in header            # ...mas o preço de mercado fica
    assert "**100**" in md                  # o total continua


def test_pricecharting_column_and_link_present():
    md = ranking_markdown([_card()], 10)
    assert "PriceCharting" in _header(md)
    assert "pricecharting.com/search-products" in md


def test_pricecharting_url_strips_era_prefix_and_keeps_number():
    url = _pricecharting_search_url("Charizard ex", "SV03: Obsidian Flames", "223")
    assert url.startswith(
        "https://www.pricecharting.com/search-products?type=prices&q=")
    assert "SV03" not in url                 # prefixo de era removido da query
    assert "obsidian" in url.lower()
    assert "223" in url


def test_card_without_number_has_no_dangling_hash():
    md = ranking_markdown([_card(number="")], 10)
    assert "Mew V (Alternate Full Art) #" not in md
    assert "Mew V (Alternate Full Art)" in md
