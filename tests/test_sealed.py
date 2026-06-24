"""Testes do score de produto selado."""
from datetime import date

from outlook.sealed import (msrp_points, reprint_points, score_sealed,
                            type_points)


def _prod(name="Ascended Heroes Elite Trainer Box",
          ptype="Elite Trainer Box", pid="p1"):
    return {"id": pid, "name": name, "product_type": ptype}


def _set(set_id="24541", name="ME: Ascended Heroes",
         release="2026/01/30", series="Mega Evolution"):
    return {"id": set_id, "name": name, "releaseDate": release, "series": series}


def test_type_points_ordering():
    assert type_points("Elite Trainer Box") == type_points("Booster Box") == 25
    assert type_points("Booster Bundle") < type_points("Elite Trainer Box")
    assert type_points("Mini Tin") < type_points("Booster Bundle")
    assert type_points("desconhecido") == 8


def test_msrp_points_room_vs_priced_in():
    assert msrp_points("Elite Trainer Box", 60.0) == 25     # 1.0x: espaço máximo
    assert msrp_points("Elite Trainer Box", 174.0) == 10    # ~2.9x (AH hoje)
    assert msrp_points("Booster Bundle", 150.0) == 5        # ~5.6x: precificado
    assert msrp_points("unknown-type", 999.0) == 12         # neutro sem MSRP


def test_reprint_points():
    assert reprint_points(True) == 6
    assert reprint_points(False) == 25


def test_score_sealed_ah_etb_is_heavy_reprint():
    sc = score_sealed(_prod(), _set(), market_usd=174.0, today=date(2026, 6, 16))
    assert sc.heavy_reprint                 # set especial detectado
    assert sc.pts_reprint == 6
    assert sc.pts_type == 25                # ETB
    assert sc.pts_msrp == 10                # ~2.9x MSRP
    assert round(sc.msrp_multiple, 1) == 2.9
    assert sc.score == sc.pts_type + sc.pts_age + sc.pts_msrp + sc.pts_reprint


def test_score_sealed_normal_set_keeps_supply_upside():
    # set NORMAL: reprint=25 (oferta encolhe ao sair de catálogo)
    s = _set(set_id="sv07", name="SV07: Stellar Crown", release="2024/09/13")
    sc = score_sealed(_prod(name="Stellar Crown ETB"), s, market_usd=70.0,
                      today=date(2026, 6, 16))
    assert not sc.heavy_reprint
    assert sc.pts_reprint == 25
