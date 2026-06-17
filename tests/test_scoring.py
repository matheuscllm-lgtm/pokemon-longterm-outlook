"""Testes do score de longo prazo — componentes e invariantes."""
from datetime import date

from outlook.scoring import (HEAVY_REPRINT_SET_IDS, price_points,
                             rarity_points, score_card, supply_points)

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


def test_score_card_trainer_now_scores_appeal():
    # Marnie SIR: treinador antes caía em 8; agora tier S = 25 no Personagem.
    sc = score_card(_card(name="Marnie", rarity="Special Illustration Rare"),
                    _set(), market_usd=80.0, today=TODAY)
    assert sc.notorious == "Marnie"
    assert sc.pts_character == 25
    assert sc.score == 25 + 25 + 18 + 25   # 93


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
