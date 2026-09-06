"""Testes de outlook.availability — helpers puros + filtro NM-EN do CT (sem rede)."""
import pytest

from outlook.availability import (CTAvailability, _base_name, _clean_number,
                                  _clean_secret, comc_url, ebay_url, liga_url,
                                  load_ct_jwt, myp_url, verdict_nm_en)


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
    assert "umbreon" in ebay_url("Umbreon VMAX", "SWSH07: Evolving Skies", "214").lower()
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


def test_cheapest_unknown_number_above_set_range_flags_wrong_set(monkeypatch):
    # nº 999 > máx 214 do set casado → autodetecção de provável set errado
    # (a classe de bug do "Base Set" WotC vira erro autodeclarado, não um
    # "carta não encontrada" genérico).
    ct = _ct_with_fake_api(monkeypatch, LISTINGS)
    r = ct.cheapest("SWSH07: Evolving Skies", "999")
    assert "nº 999 > máx 214" in r["status"]
    assert "provável set errado" in r["status"]


def test_cheapest_unknown_number_within_range_is_plain_not_found(monkeypatch):
    ct = CTAvailability("jwt-fake")

    def fake_get(path, **params):
        if path == "/expansions":
            return [{"id": 11, "name": "Evolving Skies", "game_id": 5}]
        if path == "/blueprints/export":
            return [{"id": 1, "fixed_properties": {"collector_number": "100"}},
                    {"id": 2, "fixed_properties": {"collector_number": "214"}}]
        raise AssertionError(f"rota inesperada: {path}")

    monkeypatch.setattr(ct, "_get", fake_get)
    r = ct.cheapest("SWSH07: Evolving Skies", "150")   # dentro da faixa
    assert r["status"] == "carta não encontrada no CT"


def test_cheapest_letter_number_not_found_is_plain(monkeypatch):
    # nº com letra (TG12) não entra na comparação numérica — sem falso alarme
    ct = _ct_with_fake_api(monkeypatch, LISTINGS)
    r = ct.cheapest("SWSH07: Evolving Skies", "TG99")
    assert r["status"] == "carta não encontrada no CT"


def test_to_usd_eur_uses_rates_without_network():
    ct = CTAvailability("jwt-fake")
    ct._usd_rates = {"EUR": 0.90}                 # 1 USD = 0.90 EUR
    assert ct._to_usd(900, "EUR") == pytest.approx(10.0)
    assert ct._to_usd(500, "USD") == pytest.approx(5.0)


# ── desambiguação de blueprint pelo nome (bug real: Venusaur ex a $0.16) ─────
def test_blueprint_prefers_name_match_among_same_number(monkeypatch):
    ct = CTAvailability("jwt-fake")

    def fake_get(path, **params):
        if path == "/expansions":
            # nome REAL da expansão no CT é só "151" (o override aponta pra cá)
            return [{"id": 5, "name": "151", "game_id": 5}]
        if path == "/blueprints/export":
            # dois blueprints no MESMO número: o errado vem primeiro
            return [
                {"id": 1, "name": "Basic Grass Energy",
                 "fixed_properties": {"collector_number": "198"}},
                {"id": 2, "name": "Venusaur ex",
                 "fixed_properties": {"collector_number": "198"}},
            ]
        if path == "/marketplace/products":
            # só responde pro blueprint certo — se pedir o errado, o teste falha
            assert params["blueprint_id"] == 2
            return {"2": [{"properties_hash": {"condition": "Near Mint",
                                               "pokemon_language": "en"},
                           "graded": False,
                           "price": {"cents": 9000, "currency": "USD"},
                           "quantity": 1}]}
        raise AssertionError(f"rota inesperada: {path}")

    monkeypatch.setattr(ct, "_get", fake_get)
    r = ct.cheapest("SV: Scarlet & Violet 151", "198/165",
                    "Venusaur ex (Special Illustration Rare)")
    assert r["status"] == "ok"
    assert r["usd"] == pytest.approx(90.0)


def test_blueprint_without_name_falls_back_to_first(monkeypatch):
    ct = _ct_with_fake_api(monkeypatch, LISTINGS)
    r = ct.cheapest("SWSH07: Evolving Skies", "214")   # sem card_name: como antes
    assert r["status"] == "ok"


def test_base_name_strips_descriptors():
    assert _base_name("Venusaur ex (Alternate Full Art)") == "venusaur ex"
    assert _base_name("Mew V (Alternate Full Art)") == "mew v"
    assert _base_name("Iono") == "iono"


# ── veredito NM-EN: honesto por construção ───────────────────────────────────
def test_verdict_ct_cheaper_within_sanity_wins():
    v = verdict_nm_en(46.01, 58.25)
    assert v.startswith("**CardTrader** US$ 46.01")


def test_verdict_too_good_is_suspect_not_winner():
    # caso real do run: Venusaur ex ref $118.73, CT $0.16 → nunca "vencedor"
    v = verdict_nm_en(0.16, 118.73)
    assert "suspeito" in v
    assert "CardTrader**" not in v


def test_verdict_ct_above_ref_does_not_crown_tcgplayer():
    # A ref market NÃO é anúncio comprável — o veredito constata que o CT
    # está acima, sem declarar "TCGPlayer" vencedor (auditoria 2026-07-13).
    v = verdict_nm_en(148.06, 109.68)
    assert "TCGPlayer**" not in v
    assert "35% acima" in v
    assert "não anúncio" in v


def test_verdict_without_ct_source_is_honest_nd():
    assert "CT_JWT" in verdict_nm_en(None, 50.0, has_ct=False)
    v = verdict_nm_en(None, 50.0, ct_status="sem oferta EN+NM", has_ct=True)
    assert v.startswith("n/d — CT: sem oferta EN+NM")


# ── filtro de anúncio-lixo (caso real: SIR de $118 "vendida" a R$ 0,89) ──────
JUNK = {"properties_hash": {"condition": "Near Mint", "pokemon_language": "en"},
        "graded": False, "price": {"cents": 16, "currency": "USD"},
        "quantity": 24}
REAL = {"properties_hash": {"condition": "Near Mint", "pokemon_language": "en"},
        "graded": False, "price": {"cents": 14100, "currency": "USD"},
        "quantity": 2}


def test_cheapest_with_ref_skips_junk_and_reports_next_plausible(monkeypatch):
    ct = _ct_with_fake_api(monkeypatch, [JUNK, REAL])
    r = ct.cheapest("SWSH07: Evolving Skies", "214", ref_usd=118.73)
    assert r["status"] == "ok"
    assert r["usd"] == pytest.approx(141.0)       # a plausível, não o lixo
    assert r["junk_skipped"] == 1


def test_cheapest_only_junk_is_labeled_not_zero(monkeypatch):
    ct = _ct_with_fake_api(monkeypatch, [JUNK])
    r = ct.cheapest("SWSH07: Evolving Skies", "214", ref_usd=118.73)
    assert r["status"] == "só anúncios-lixo (1 < 50% da ref)"
    assert "usd" not in r


def test_cheapest_without_ref_keeps_old_behavior(monkeypatch):
    ct = _ct_with_fake_api(monkeypatch, [JUNK, REAL])
    r = ct.cheapest("SWSH07: Evolving Skies", "214")
    assert r["usd"] == pytest.approx(0.16)        # sem ref não filtra (backstop
    assert r["junk_skipped"] == 0                 # é o gate do veredito)


# ── override de nome de set (caso provado: 151 caía no set base via fuzzy) ───
def test_expansion_override_beats_greedy_contains():
    ct = CTAvailability("jwt-fake")
    ct._expansions = [
        {"id": 100, "name": "Scarlet & Violet", "game_id": 5},   # o fuzzy pegava este
        {"id": 200, "name": "151", "game_id": 5},                # o certo no CT
    ]
    assert ct.find_expansion_id("SV: Scarlet & Violet 151") == 200
    # e o set base continua indo pro set base
    assert ct.find_expansion_id("SV01: Scarlet & Violet Base Set") == 100


def test_expansion_override_without_target_is_none_not_wrong_set():
    ct = CTAvailability("jwt-fake")
    ct._expansions = [{"id": 100, "name": "Scarlet & Violet", "game_id": 5}]
    assert ct.find_expansion_id("SV: Scarlet & Violet 151") is None


# ── falsos matches de set provados no run 2026-07-13 ─────────────────────────
def test_base_set_suffix_never_matches_wotc_base_set():
    # "SV01: Scarlet & Violet Base Set" caía no "Base Set" WotC de 1999
    # (contains first-hit) → carta chase saía "não encontrada" — ou, pior,
    # nº coincidente casaria carta ERRADA em silêncio.
    ct = CTAvailability("jwt-fake")
    ct._expansions = [
        {"id": 1472, "name": "Base Set", "game_id": 5},          # WotC 1999
        {"id": 3239, "name": "Scarlet & Violet", "game_id": 5},
        {"id": 1623, "name": "Sword & Shield", "game_id": 5},
    ]
    assert ct.find_expansion_id("SV01: Scarlet & Violet Base Set") == 3239
    assert ct.find_expansion_id("SWSH01: Sword & Shield Base Set") == 1623


def test_pokemon_go_matches_international_set_not_japanese():
    # "Pokemon GO" caía no "Pokémon GO Enhanced Expansion Pack" (set JP
    # s10b) → "sem oferta EN+NM" enganoso; o internacional é o pkmgo.
    ct = CTAvailability("jwt-fake")
    ct._expansions = [
        {"id": 3057, "name": "Pokémon GO Enhanced Expansion Pack", "game_id": 5},
        {"id": 3058, "name": "Pokémon TCG: Pokémon GO", "game_id": 5},
    ]
    assert ct.find_expansion_id("Pokemon GO") == 3058


def test_contains_ranked_prefers_most_specific_contained_name():
    # Sem override: entre nomes CT contidos no alvo, vence o mais LONGO
    # (mais específico) — não o primeiro da lista da API.
    ct = CTAvailability("jwt-fake")
    ct._expansions = [
        {"id": 1, "name": "Zenith", "game_id": 5},               # genérico 1º
        {"id": 2, "name": "Crown Zenith", "game_id": 5},
    ]
    assert ct.find_expansion_id("SWSH: Crown Zenith: Galarian Gallery") == 2


def test_contains_ranked_prefers_shortest_containing_name():
    # Alvo contido em vários nomes CT: vence o mais CURTO (menos sufixo).
    ct = CTAvailability("jwt-fake")
    ct._expansions = [
        {"id": 1, "name": "Temporal Forces Enhanced Booster Pack", "game_id": 5},
        {"id": 2, "name": "SV: Temporal Forces", "game_id": 5},
    ]
    assert ct.find_expansion_id("Temporal Forces") == 2


# ── retry de erro transiente do CT (caso real: 401 isolado entre 2 runs) ─────
def test_ct_get_retries_transient_error_then_succeeds(monkeypatch):
    import outlook.availability as av

    calls = {"n": 0}

    class FakeResp:
        def __init__(self, status, payload=None):
            self.status_code = status
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResp(401)              # blip transiente observado
        return FakeResp(200, {"ok": True})

    monkeypatch.setattr(av.requests, "get", fake_get)
    monkeypatch.setattr(av.time, "sleep", lambda s: None)
    ct = CTAvailability("jwt-fake")
    assert ct._get("/expansions") == {"ok": True}
    assert calls["n"] == 2


def test_ct_get_persistent_error_still_raises(monkeypatch):
    import outlook.availability as av

    class FakeResp:
        status_code = 500

        def json(self):  # pragma: no cover
            return {}

    monkeypatch.setattr(av.requests, "get",
                        lambda *a, **k: FakeResp())
    monkeypatch.setattr(av.time, "sleep", lambda s: None)
    ct = CTAvailability("jwt-fake")
    with pytest.raises(RuntimeError, match="CT HTTP 500"):
        ct._get("/expansions")
