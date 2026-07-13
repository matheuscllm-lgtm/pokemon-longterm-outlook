"""Testes de outlook.comc_availability — parser carddata + filtros (sem rede).

A fixture reproduz o DOM REAL da página de busca da COMC (blocos
`<div class="carddata">` com o link de detalhe carregando
set/número/nome/condição no path) — formato provado no scanner-comc da frota.
"""
import pytest

from outlook.comc_availability import (COMCAvailability, comc_search_url,
                                       load_firecrawl_key, parse_comc_page)


def _block(year, set_seg, num, name, item_id, graded, cond, qty, price):
    return f'''
<div class="carddata">
  <div class="description">{set_seg.replace('_', ' ')} #{num}</div>
  <h3 class="title">
    <a href="https://www.comc.com/Cards/Pokemon/{year}/{set_seg}/{num}/{name}/{item_id}/{graded}/COMC/{cond}">{name.replace('_', ' ')} [{cond}]</a>
  </h3>
  <div class="listprice">
    <div class="qty">{qty} from </div>
    <a title="View Sales Data">${price}<i class="icon-chart-bar"></i></a>
  </div>
</div>'''


FIXTURE = (
    '<div id="cardexplorer">'
    # LP (fora da allowlist NM) — tem que ser ignorada
    + _block(2021, "Evolving_Skies", "215", "Umbreon_VMAX", 111, "Ungraded", "VG", 1, "60.00")
    # graded — fora
    + _block(2021, "Evolving_Skies", "215", "Umbreon_VMAX", 222, "Graded", "EX-NM", 1, "55.00")
    # set japonês — fora (referência é o produto EN)
    + _block(2021, "Japanese_Eevee_Heroes", "215", "Umbreon_VMAX", 333, "Ungraded", "EX-NM", 1, "40.00")
    # número errado — fora
    + _block(2021, "Evolving_Skies", "214", "Umbreon_VMAX", 444, "Ungraded", "EX-NM", 1, "50.00")
    # lixo (< 50% da ref 100) — contado, nunca vencedor
    + _block(2021, "Evolving_Skies", "215", "Umbreon_VMAX", 555, "Ungraded", "EX-NM", 1, "3.25")
    # plausível mais cara
    + _block(2021, "Evolving_Skies", "215", "Umbreon_VMAX", 666, "Ungraded", "EX-NM", 2, "110.50")
    # plausível MAIS BARATA — vencedora
    + _block(2021, "Evolving_Skies", "215", "Umbreon_VMAX", 777, "Ungraded", "NM", 3, "95.99")
    + '</div>'
)


def test_parse_comc_page_extracts_all_blocks():
    listings = parse_comc_page(FIXTURE)
    assert len(listings) == 7
    first = listings[0]
    assert first["name"] == "Umbreon VMAX"
    assert first["set"] == "Evolving Skies"
    assert first["number"] == "215"
    assert first["condition"] == "VG"
    assert first["graded"] is False
    assert first["price"] == pytest.approx(60.0)
    assert first["qty"] == 1
    assert first["url"].startswith("https://www.comc.com/Cards/Pokemon/")


def test_parse_comc_page_marks_graded_from_url_segment():
    listings = parse_comc_page(FIXTURE)
    assert listings[1]["graded"] is True


def _comc_with_fake_fetch(monkeypatch, html):
    c = COMCAvailability("key-fake")
    monkeypatch.setattr(c, "_fetch", lambda url: html)
    return c


def test_cheapest_filters_condition_graded_language_number(monkeypatch):
    c = _comc_with_fake_fetch(monkeypatch, FIXTURE)
    r = c.cheapest("Umbreon VMAX", "215/203", ref_usd=100.0)
    assert r["status"] == "ok"
    assert r["usd"] == pytest.approx(95.99)   # NM plausível mais barata
    assert r["qty"] == 3
    assert r["junk_skipped"] == 1


def test_cheapest_only_junk_is_labeled(monkeypatch):
    junk_html = ('<div id="cardexplorer">'
                 + _block(2021, "Evolving_Skies", "215", "Umbreon_VMAX",
                          555, "Ungraded", "EX-NM", 1, "3.25") + '</div>')
    c = _comc_with_fake_fetch(monkeypatch, junk_html)
    r = c.cheapest("Umbreon VMAX", "215", ref_usd=100.0)
    assert r["status"].startswith("só listagens-lixo (1")
    assert "usd" not in r


def test_cheapest_no_match_is_labeled(monkeypatch):
    c = _comc_with_fake_fetch(monkeypatch, FIXTURE)
    r = c.cheapest("Umbreon VMAX", "999", ref_usd=100.0)
    assert r == {"status": "sem listagem EX-NM EN no nº"}


def test_cheapest_empty_page_is_labeled(monkeypatch):
    c = _comc_with_fake_fetch(monkeypatch, '<div id="cardexplorer"></div>')
    r = c.cheapest("Umbreon VMAX", "215")
    assert r == {"status": "carta não encontrada na COMC"}


def test_cheapest_fetch_error_is_labeled_not_raised(monkeypatch):
    c = COMCAvailability("key-fake")

    def boom(url):
        raise RuntimeError("COMC atrás de challenge Cloudflare")

    monkeypatch.setattr(c, "_fetch", boom)
    r = c.cheapest("Umbreon VMAX", "215")
    assert r["status"] == "erro: COMC atrás de challenge Cloudflare"


def test_search_url_carries_server_side_filters():
    url = comc_search_url("Umbreon VMAX")
    assert "Umbreon+VMAX" in url
    assert ",fb," in url          # Buy It Now
    assert ",aUngraded," in url   # sem graded
    assert ",gEX-NM," in url      # banda near-mint da COMC
    assert ",sl," in url          # menor preço primeiro


def test_load_firecrawl_key_absent_is_none(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    assert load_firecrawl_key() is None


def test_load_firecrawl_key_strips_bom(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "﻿fc-key​")
    assert load_firecrawl_key() == "fc-key"
