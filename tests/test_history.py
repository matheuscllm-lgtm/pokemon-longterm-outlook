"""Testes da persistência de snapshots (history.py)."""
from datetime import date

from outlook import history
from outlook.scoring import score_card


def _scored(market):
    card = {"id": "c1", "name": "Pikachu ex",
            "rarity": "Special Illustration Rare", "number": "276"}
    smeta = {"id": "24541", "name": "ME: Ascended Heroes",
             "releaseDate": "2026/01/30", "series": "Mega Evolution"}
    return score_card(card, smeta, market, today=date(2026, 6, 1))


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "SNAP_DIR", tmp_path)
    history.save_snapshot([_scored(100.0)], when=date(2026, 6, 1))
    assert len(history.list_snapshots()) == 1
    rows = history.load_rows()
    assert len(rows) == 1 and rows[0]["card_id"] == "c1"
    assert rows[0]["market_usd"] == "100.00"


def test_price_change_two_snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "SNAP_DIR", tmp_path)
    history.save_snapshot([_scored(100.0)], when=date(2026, 6, 1))
    history.save_snapshot([_scored(120.0)], when=date(2026, 6, 21))
    ch = history.price_change("c1")
    assert ch is not None
    pct, days = ch
    assert round(pct, 1) == 20.0
    assert days == 20


def test_price_change_needs_two(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "SNAP_DIR", tmp_path)
    history.save_snapshot([_scored(100.0)], when=date(2026, 6, 1))
    assert history.price_change("c1") is None
