"""Testes de outlook.ebay_availability — filtros e honestidade (sem rede)."""
import pytest

from outlook.ebay_availability import (EbayAvailability, _title_excluded,
                                       _title_matches, load_ebay_keys)


# ── chaves: env vars sanitizadas; ausência = None honesto ────────────────────
def test_load_ebay_keys_absent_is_none(monkeypatch):
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("EBAY_CLIENT_SECRET", raising=False)
    assert load_ebay_keys() is None


def test_load_ebay_keys_strips_bom(monkeypatch):
    monkeypatch.setenv("EBAY_CLIENT_ID", "﻿id-limpo")
    monkeypatch.setenv("EBAY_CLIENT_SECRET", " secret ​")
    assert load_ebay_keys() == ("id-limpo", "secret")


def test_load_ebay_keys_partial_is_none(monkeypatch):
    monkeypatch.setenv("EBAY_CLIENT_ID", "id")
    monkeypatch.delenv("EBAY_CLIENT_SECRET", raising=False)
    assert load_ebay_keys() is None


# ── guards de título (match por busca: precisão > cobertura) ─────────────────
def test_title_must_contain_collector_number():
    assert _title_matches("Pokemon Mew V 251/264 Fusion Strike Alt Art", "251")
    assert _title_matches("Mimikyu V TG16 Brilliant Stars", "TG16")
    assert not _title_matches("Umbreon VMAX Evolving Skies #215", "214")
    assert not _title_matches("Umbreon VMAX 2149 lot", "214")   # 214 ⊄ 2149


def test_title_number_ignores_leading_zeros():
    # tcgcsv traz "072"; título real costuma trazer "72/78" ou "072/078"
    assert _title_matches("Mewtwo V 72/78 Pokemon GO Alt Art", "072")


def test_title_excluded_graded_and_non_en():
    assert _title_excluded("Mew V 251 PSA 10 GEM MINT")
    assert _title_excluded("Charizard V 154 Japanese Brilliant Stars")
    assert not _title_excluded("Mew V 251/264 Alternate Full Art NM")


# ── cheapest: filtros + lixo + honestidade ────────────────────────────────────
ITEMS = [
    # sem o número no título → fora
    {"title": "Pokemon Mew V Fusion Strike Alt Art",
     "price": {"value": "90.00", "currency": "USD"}, "itemWebUrl": "u0"},
    # graded → fora
    {"title": "Mew V 251/264 PSA 9",
     "price": {"value": "95.00", "currency": "USD"}, "itemWebUrl": "u1"},
    # japonesa → fora
    {"title": "Mew V 251 Japanese Fusion Arts",
     "price": {"value": "40.00", "currency": "USD"}, "itemWebUrl": "u2"},
    # lixo (< 50% da ref 100) → contado, nunca vencedor
    {"title": "Mew V 251/264 Fusion Strike damaged? proxy",
     "price": {"value": "5.00", "currency": "USD"}, "itemWebUrl": "u3"},
    # plausível mais cara
    {"title": "Mew V 251/264 Fusion Strike Alt Art NM",
     "price": {"value": "120.00", "currency": "USD"}, "itemWebUrl": "u4"},
    # plausível MAIS BARATA — vencedora
    {"title": "Pokemon Mew V 251/264 Alternate Full Art",
     "price": {"value": "99.00", "currency": "USD"}, "itemWebUrl": "u5"},
]


def _ebay_with_fake_search(monkeypatch, items):
    e = EbayAvailability("id", "secret")
    monkeypatch.setattr(e, "_search", lambda q: items)
    return e


def test_cheapest_picks_min_plausible_with_number_in_title(monkeypatch):
    e = _ebay_with_fake_search(monkeypatch, ITEMS)
    r = e.cheapest("Mew V (Alternate Full Art)", "SWSH08: Fusion Strike",
                   "251", ref_usd=100.0)
    assert r["status"] == "ok"
    assert r["usd"] == pytest.approx(99.0)
    assert r["url"] == "u5"
    assert r["junk_skipped"] == 1


def test_cheapest_only_junk_is_labeled(monkeypatch):
    junk_only = [ITEMS[3]]
    e = _ebay_with_fake_search(monkeypatch, junk_only)
    r = e.cheapest("Mew V", "SWSH08: Fusion Strike", "251", ref_usd=100.0)
    assert r["status"].startswith("só anúncios-lixo (1")
    assert "usd" not in r


def test_cheapest_nothing_plausible_is_labeled(monkeypatch):
    e = _ebay_with_fake_search(monkeypatch, ITEMS[:3])
    r = e.cheapest("Mew V", "SWSH08: Fusion Strike", "251", ref_usd=100.0)
    assert r == {"status": "sem anúncio plausível"}


def test_cheapest_search_error_is_labeled_not_raised(monkeypatch):
    e = EbayAvailability("id", "secret")

    def boom(q):
        raise RuntimeError("eBay HTTP 500")

    monkeypatch.setattr(e, "_search", boom)
    r = e.cheapest("Mew V", "SWSH08: Fusion Strike", "251")
    assert r["status"] == "erro: eBay HTTP 500"


def test_cheapest_non_usd_listing_is_skipped(monkeypatch):
    e = _ebay_with_fake_search(monkeypatch, [
        {"title": "Mew V 251/264", "price": {"value": "50.00", "currency": "EUR"},
         "itemWebUrl": "u9"}])
    r = e.cheapest("Mew V", "SWSH08: Fusion Strike", "251")
    assert r == {"status": "sem anúncio plausível"}


def test_token_is_cached_until_expiry(monkeypatch):
    import outlook.ebay_availability as ea

    calls = {"n": 0}

    class FakeResp:
        status_code = 200

        def json(self):
            return {"access_token": f"tok-{calls['n']}", "expires_in": 7200}

    def fake_post(url, auth=None, data=None, timeout=None):
        calls["n"] += 1
        return FakeResp()

    monkeypatch.setattr(ea.requests, "post", fake_post)
    e = EbayAvailability("id", "secret")
    assert e._get_token() == "tok-1"
    assert e._get_token() == "tok-1"      # cache: não refaz o POST
    assert calls["n"] == 1
