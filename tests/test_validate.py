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


def test_backtest_lowpop_mede_retorno_no_psa10_e_declara_o_criterio(monkeypatch):
    # Modo low pop: o operador compra o SLAB, então o retorno que valida a
    # régua é o do PSA 10, não o da carta crua. Critério de sucesso (decisão
    # 2026-09-22): em janela ≥ 180 dias, Spearman(score, retorno PSA 10) > 0 E
    # mediana do top-quartil > mediana do bottom-quartil.
    rows = []
    for i in range(12):
        cid = f"c{i}"
        base = {"card_id": cid, "score": str(30 + i * 5), "lowpop": "1",
                "market_usd": "100.00"}           # crua PARADA de propósito
        rows.append({**base, "date": "2026-03-01", "psa10_usd": "200.00"})
        rows.append({**base, "date": "2026-09-01", "psa10_usd": f"{200.0 + i * 10:.2f}"})
    monkeypatch.setattr(history, "load_rows", lambda: rows)
    out = validate.backtest_longitudinal()
    assert "PSA 10" in out and "+1.00" in out          # mediu no slab
    assert "Critério de sucesso" in out and "ATINGIDO" in out


def test_backtest_lowpop_janela_curta_nao_declara_sucesso(monkeypatch):
    rows = []
    for i in range(12):
        base = {"card_id": f"c{i}", "score": str(30 + i * 5), "lowpop": "1",
                "market_usd": "100.00"}
        rows.append({**base, "date": "2026-09-01", "psa10_usd": "200.00"})
        rows.append({**base, "date": "2026-09-22", "psa10_usd": f"{200.0 + i:.2f}"})
    monkeypatch.setattr(history, "load_rows", lambda: rows)
    out = validate.backtest_longitudinal()
    assert "ATINGIDO" not in out and "preliminar" in out


def test_backtest_lowpop_ignora_snapshots_da_regua_antiga(monkeypatch):
    # História real do PC: snapshots raw (2026-06-28, 09-15) ANTES dos low pop.
    # A janela low pop tem que começar no 1º snapshot low pop, não no raw.
    rows = [{"date": "2026-06-28", "card_id": f"c{i}", "score": "50", "lowpop": "0",
             "market_usd": "100.00", "psa10_usd": ""} for i in range(12)]
    for i in range(12):
        base = {"card_id": f"c{i}", "score": str(30 + i * 5), "lowpop": "1",
                "market_usd": "100.00"}
        rows.append({**base, "date": "2026-09-22", "psa10_usd": "200.00"})
        rows.append({**base, "date": "2027-04-01", "psa10_usd": f"{200.0 + i * 10:.2f}"})
    monkeypatch.setattr(history, "load_rows", lambda: rows)
    out = validate.backtest_longitudinal()
    assert "2026-09-22 → 2027-04-01" in out and "ATINGIDO" in out
