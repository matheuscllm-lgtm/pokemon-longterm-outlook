"""Testes da validação/calibração do score (validate.py)."""
from datetime import date

from outlook import history, validate
from outlook.scoring import score_card


def test_spearman_monotonic():
    assert round(validate.spearman([1, 2, 3, 4], [10, 20, 30, 40]), 3) == 1.0
    assert round(validate.spearman([1, 2, 3, 4], [40, 30, 20, 10]), 3) == -1.0


def test_spearman_handles_ties():
    assert validate.spearman([1, 1, 2, 2], [5, 5, 9, 9]) == 1.0


def test_backtest_needs_history(monkeypatch):
    monkeypatch.setattr(history, "load_rows", lambda: [])
    assert "Sem snapshots" in validate.backtest_longitudinal()


def test_backtest_with_history(monkeypatch):
    rows = []
    for i in range(12):
        cid, p0, p1 = f"c{i}", 100.0, 100.0 + i  # score maior → retorno maior
        rows.append({"date": "2026-06-01", "card_id": cid,
                     "score": str(30 + i * 5), "market_usd": f"{p0:.2f}"})
        rows.append({"date": "2026-06-25", "card_id": cid,
                     "score": str(30 + i * 5), "market_usd": f"{p1:.2f}"})
    monkeypatch.setattr(history, "load_rows", lambda: rows)
    out = validate.backtest_longitudinal()
    assert "Janela" in out and "Spearman" in out
    assert "+1.00" in out  # score e retorno perfeitamente correlacionados


def test_calibrate_runs():
    smeta = {"id": "24541", "name": "ME: Ascended Heroes",
             "releaseDate": "2026/01/30", "series": "Mega Evolution"}
    cards = []
    for i in range(12):
        card = {"id": f"c{i}",
                "name": "Pikachu ex" if i % 2 else "Tinkatuff",
                "rarity": "Special Illustration Rare" if i % 2 else "Common",
                "number": str(i)}
        cards.append(score_card(card, smeta, market_usd=10.0 + i * 5,
                                today=date(2026, 6, 16)))
    out = validate.calibrate_cross_section(cards)
    assert "Calibração transversal" in out and "Spearman" in out
