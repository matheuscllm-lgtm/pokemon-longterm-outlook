"""Testes de outlook.availability — helpers puros + filtro NM-EN do CT (sem rede)."""
import pytest

from outlook.availability import (CTAvailability, _clean_number, _clean_secret,
                                  comc_url, ebay_url, liga_url, load_ct_jwt,
                                  myp_url)


# ── segredo: env var, BOM/zero-width (família de erro conhecida da frota) ────
def test_load_ct_jwt_prefers_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("CT_JWT", "token-da-env")
    env = tmp_path / ".env"
    env.write_text("CT_JWT=token-do-arquivo\n", encoding="utf-8")
    assert load_ct_jwt(env) == "token-da-env"


def test_load_ct_jwt_strips_bom_and_zero_width_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CT_JWT", "\ufeff token-limpo \u200b")
    assert load_ct_jwt(tmp_path / "inexistente.env") == "token-limpo"


def test_load_ct_jwt_reads_env_file_with_bom(monkeypatch, tmp_path):
    monkeypatch.delenv("CT_JWT", raising=False)
    env = tmp_path / ".env"
    # BOM no início da linha (Notepad salva assim) — não pode quebrar o parse.
    env.write_text("\ufeffCT_JWT=\ufefftoken-arquivo\n", encoding="utf-8")
    assert load_ct_jwt(env) == "token-arquivo"


def test_load_ct_jwt_absent_everywhere_is_none(monkeypatch, tmp_path):
    monkeypatch.delenv("CT_JWT", raising=False)
    assert load_ct_jwt(tmp_path / "inexistente.env") is None


def test_clean_secret_empty_or_invisible_only_is_none():
    assert _clean_secret("") is None
    assert _clean_secret("\ufeff\u200b") is None
    assert _clean_secret(None) is None


# ── helpers puros ─────────────────────────────────────────────────────────────
def test_clean_number_strips_denominator_and_leading_zeros():
    assert _clean_number("025/198") == "25"
    assert _clean_number("214") == "214"
    assert _clean_number("TG16") == "TG16"
    assert _clean_number("0") == "0"
    assert _clean_number("") == "0"


def test_search_urls_contain_the_card_name():
    assert "Umbreon" in ebay_url("Umbreon VMAX", "SWSH07: Evolving Skies", "214")
    assert "Umbreon" in comc_url("Umbreon VMAX")
    assert "Umbreon" in liga_url("Umbreon VMAX")
    assert "mypcards.com" in myp_url("Umbreon VMAX")  # busca Google site-restrita


# ── CTAvailability.cheapest: filtro EN + Near Mint + não-graded ──────────────
LISTINGS = [
    # LP barata — condição errada, tem que ser ignorada (match exato NM)
    {"properties_hash": {"condition": "Lightly Played", "pokemon_language": "en"},
     "graded": False, "price": {"cents": 100, "currency": "USD"}, "quantity": 3},
    # NM mas italiana — língua errada
    {"properties_hash": {"condition": "Near Mint", "pokemon_language": "it"},
     "graded": False, "price": {"cents": 200, "currency": "USD"}, "quantity": 1},
    # NM EN graded — graded fica de fora
    {"properties_hash": {"condition": "Near Mint", "pokemon_language": "en"},
     "graded": True, "price": {"cents": 300, "currency": "USD"}, "quantity": 1},
    # NM EN sem cents válido — ignorada sem quebrar
    {"properties_hash": {"condition": "Near Mint", "pokemon_language": "en"},
     "graded": False, "price": {"cents": None, "currency": "USD"}, "quantity": 1},
    # NM EN válida mais cara
    {"properties_hash": {"condition": "Near Mint", "pokemon_language": "en"},
     "graded": False, "price": {"cents": 1500, "currency": "USD"}, "quantity": 2},
    # NM EN válida MAIS BARATA — é a vencedora esperada
    {"properties_hash": {"condition": "Near Mint", "pokemon_language": "en"},
     "graded": False, "price": {"cents": 990, "currency": "USD"}, "quantity": 5},
]


def _ct_with_fake_api(monkeypatch, listings):
    ct = CTAvailability("jwt-fake")

    def fake_get(path, **params):
        if path == "/expansions":
            return [{"id": 11, "name": "Evolving Skies", "game_id": 5},
                    {"id": 99, "name": "Evolving Skies", "game_id": 1}]
        if path == "/blueprints/export":
            assert params["expansion_id"] == 11
            return [{"id": 777, "fixed_properties": {"collector_number": "214"}}]
        if path == "/marketplace/products":
            assert params["blueprint_id"] == 777
            return {"777": listings}
        raise AssertionError(f"rota inesperada: {path}")

    monkeypatch.setattr(ct, "_get", fake_get)
    return ct


def test_cheapest_picks_min_nm_en_nongraded(monkeypatch):
    ct = _ct_with_fake_api(monkeypatch, LISTINGS)
    r = ct.cheapest("SWSH07: Evolving Skies", "214/203")
    assert r["status"] == "ok"
    assert r["usd"] == pytest.approx(9.90)      # 990 cents USD, não a LP de $1
    assert r["qty"] == 5
    assert r["url"].endswith("/777")


def test_cheapest_no_nm_en_offer_is_labeled(monkeypatch):
    only_bad = [l for l in LISTINGS
                if (l["properties_hash"]["condition"] != "Near Mint"
                    or l["properties_hash"]["pokemon_language"] != "en"
                    or l["graded"])]
    ct = _ct_with_fake_api(monkeypatch, only_bad)
    r = ct.cheapest("SWSH07: Evolving Skies", "214")
    assert r == {"status": "sem oferta EN+NM"}


def test_cheapest_unknown_set_is_labeled(monkeypatch):
    ct = _ct_with_fake_api(monkeypatch, LISTINGS)
    r = ct.cheapest("Set Que Não Existe", "214")
    assert r["status"] == "set não mapeado no CT"


def test_cheapest_unknown_number_is_labeled(monkeypatch):
    ct = _ct_with_fake_api(monkeypatch, LISTINGS)
    r = ct.cheapest("SWSH07: Evolving Skies", "999")
    assert r["status"] == "carta não encontrada no CT"


def test_to_usd_eur_uses_rates_without_network():
    ct = CTAvailability("jwt-fake")
    ct._usd_rates = {"EUR": 0.90}                 # 1 USD = 0.90 EUR
    assert ct._to_usd(900, "EUR") == pytest.approx(10.0)
    assert ct._to_usd(500, "USD") == pytest.approx(5.0)
