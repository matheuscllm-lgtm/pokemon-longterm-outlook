"""Testes do score de longo prazo — componentes e invariantes."""
from datetime import date

from outlook.scoring import (HEAVY_REPRINT_SET_IDS, is_heavy_reprint,
                             price_points, rarity_points, score_card,
                             supply_points)

TODAY = date(2026, 6, 12)


def _card(name="Umbreon ex", rarity="Special Illustration Rare", number="161"):
    return {"id": "tst-1", "name": name, "rarity": rarity, "number": number}


def _set(set_id="sv7", release="2024/09/13", series="Scarlet & Violet"):
    return {"id": set_id, "name": "Stellar Crown", "releaseDate": release,
            "series": series}


def test_rarity_tiers_ordering():
    assert rarity_points("Special Illustration Rare") > rarity_points("Illustration Rare")
    assert rarity_points("Illustration Rare") > rarity_points("Hyper Rare")
    assert rarity_points("Hyper Rare") > rarity_points("Rare Holo VMAX")
    assert rarity_points("Common") == 3
    # nomes SWSH com "Secret"/"Rainbow" caem no tier gold
    assert rarity_points("Rare Secret") == 14
    assert rarity_points("Rare Rainbow") == 14


def test_supply_grows_with_age_and_reprint_caps():
    old = supply_points(date(2021, 8, 27), TODAY, heavy_reprint=False)   # EVS ~57m
    mid = supply_points(date(2024, 9, 13), TODAY, heavy_reprint=False)   # ~21m
    new = supply_points(date(2026, 5, 1), TODAY, heavy_reprint=False)    # ~1m
    assert old > mid > new
    assert old == 25
    # reprint forte: teto 12 mesmo em set velho
    assert supply_points(date(2021, 8, 27), TODAY, heavy_reprint=True) == 12


def test_price_sweet_spot():
    assert price_points(80.0) == 25            # sweet spot
    assert price_points(25.0) == 20
    assert price_points(2.0) == 5              # bulk sem liquidez
    assert price_points(500.0) == 12           # já precificado
    assert price_points(80.0) > price_points(500.0)


def test_score_card_full_and_notorious():
    sc = score_card(_card(), _set(), market_usd=80.0, today=TODAY)
    # Umbreon é notório (25) + SIR (25) + ~21m (18) + $80 (25) = 93
    assert sc.notorious == "Umbreon"
    assert sc.score == 93
    assert sc.pts_character == 25


def test_score_card_non_notorious_bulk():
    sc = score_card(_card(name="Tinkatuff", rarity="Common"),
                    _set(), market_usd=6.0, today=TODAY)
    assert sc.notorious is None
    assert sc.pts_character == 8
    assert sc.score == 8 + 3 + 18 + 12


def test_heavy_reprint_flagged():
    sc = score_card(_card(name="Charizard ex"),
                    _set(set_id="sv3pt5", release="2023/09/22"),
                    market_usd=100.0, today=TODAY)
    assert sc.heavy_reprint
    assert sc.pts_supply == 12
    assert any("reprint" in n for n in sc.notes)
    assert "sv3pt5" in HEAVY_REPRINT_SET_IDS


def test_rarity_mega_era_tiers():
    # bug corrigido: "Mega Attack Rare" não pode cair no default (3 = comum)
    assert rarity_points("Mega Attack Rare") == 16
    assert rarity_points("Mega Attack Rare") > rarity_points("Double Rare")
    # "Mega Hyper Rare" continua no tier gold via "hyper"
    assert rarity_points("Mega Hyper Rare") == 14
    # SIR da era Mega segue no topo
    assert rarity_points("Special Illustration Rare") == 25


def test_special_set_detected_as_heavy_reprint():
    # sets especiais (sem número no prefixo) → oferta não encolhe
    assert is_heavy_reprint("24541", "ME: Ascended Heroes")
    assert is_heavy_reprint("999", "SV: Prismatic Evolutions")
    assert is_heavy_reprint("999", "SWSH: Crown Zenith")
    # mains numerados NÃO são reprint forte por este critério
    assert not is_heavy_reprint("24380", "ME01: Mega Evolution")
    assert not is_heavy_reprint("999", "SV05: Temporal Forces")
    assert not is_heavy_reprint("999", "SWSH09: Brilliant Stars")


def test_ascended_heroes_supply_capped_when_old():
    # AH é especial → mesmo envelhecendo, supply trava em 12 (não credita
    # "oferta encolhendo" a um set impresso em massa)
    ah = _set(set_id="24541", release="2026/01/30", series="Mega Evolution")
    ah["name"] = "ME: Ascended Heroes"
    sc = score_card(_card(name="Pikachu ex"), ah, market_usd=100.0,
                    today=date(2029, 1, 30))  # 3 anos depois
    assert sc.heavy_reprint
    assert sc.pts_supply == 12
