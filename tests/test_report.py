"""Testes do formato de entrega (report.ranking_markdown) — colunas e links.

Travam as três mudanças pedidas no modo de entrega: (1) número junto ao nome,
(2) colunas de componente fora da tabela, (3) coluna de link do PriceCharting.
"""
from datetime import date

from outlook.report import (_md_link, _pricecharting_search_url,
                            ranking_markdown)
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


def test_md_link_encodes_table_breaking_chars():
    # '|' quebraria a célula da tabela; '(' / ')' sem par fechariam o link cedo.
    out = _md_link("TCG", "https://x.com/a(b)c|d")
    assert out == "[TCG](https://x.com/a%28b%29c%7Cd)"
    dest = out[out.index("](") + 2:-1]
    assert not any(ch in dest for ch in "|()")


def test_md_link_passes_clean_url_through():
    url = "https://www.tcgplayer.com/product/253147/pokemon-mew-v"
    assert _md_link("TCG", url) == f"[TCG]({url})"


def test_ranking_uses_shared_pricecharting_base():
    # A base da URL é a mesma do módulo pricecharting (fonte única, sem duplicar).
    from outlook.pricecharting import SEARCH
    base = SEARCH.split("{q}")[0]
    assert base in ranking_markdown([_card()], 10)
