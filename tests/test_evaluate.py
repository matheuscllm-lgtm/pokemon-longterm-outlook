"""Testes do avaliador de calibração — estatística pura, sem rede.

Dados sintéticos com correlação conhecida; valida Spearman/Pearson, o trato de
empates e variância-zero, e o contrato do payload do ASI-Evolve.
"""
from datetime import date

import pytest

from outlook.evaluate import (MIN_N, Calibration, _avg_ranks, calibrate,
                              calibration_markdown, evaluator_payload,
                              pearson, spearman)
from outlook.ptcg_api import cardmarket_trend_pct
from outlook.scoring import ScoredCard


def _sc(char=8, rar=8, sup=8, pri=8):
    return ScoredCard(card_id="x", name="n", set_name="s", set_id="i",
                      number="1", rarity="r", series="Scarlet & Violet",
                      release=date(2024, 1, 1), market_usd=50.0,
                      pts_character=char, pts_rarity=rar,
                      pts_supply=sup, pts_price=pri)


def test_avg_ranks_handles_ties():
    assert _avg_ranks([10, 20, 30]) == [1.0, 2.0, 3.0]
    assert _avg_ranks([10, 10, 30]) == [1.5, 1.5, 3.0]
    assert _avg_ranks([5, 5, 5]) == [2.0, 2.0, 2.0]


def test_pearson_and_spearman_extremes():
    assert pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)
    # Spearman pega monotonia não-linear (Pearson não daria 1.0 aqui).
    assert spearman([1, 2, 3, 4], [1, 10, 100, 1000]) == pytest.approx(1.0)


def test_corr_none_guards():
    assert spearman([1], [1]) is None              # N<2
    assert spearman([1, 2], [5, 5]) is None        # variância zero
    assert pearson([], []) is None


def test_calibrate_perfect_positive_and_sufficient():
    pairs = [(_sc(char=i, rar=i, sup=i, pri=i), float(i)) for i in range(1, 13)]
    cal = calibrate(pairs)
    assert cal.n == 12 and cal.n_total == 12
    assert cal.fitness == pytest.approx(1.0)
    assert cal.sufficient
    assert all(v == pytest.approx(1.0) for v in cal.by_component.values())
    assert cal.mean_trend == pytest.approx(sum(range(1, 13)) / 12)


def test_calibrate_negative_and_constant_components():
    # Personagem sobe com o realizado; Preço desce; Raridade constante (n/d).
    pairs = [(_sc(char=i, rar=20, sup=i, pri=13 - i), float(i))
             for i in range(1, 13)]
    cal = calibrate(pairs)
    assert cal.by_component["Personagem"] == pytest.approx(1.0)
    assert cal.by_component["Preço"] == pytest.approx(-1.0)
    assert cal.by_component["Raridade"] is None     # variância zero -> None


def test_insufficient_sample_blocks_recalibration():
    pairs = [(_sc(char=i), float(i)) for i in range(1, 5)]   # N=4 < MIN_N
    cal = calibrate(pairs)
    assert cal.fitness is not None        # ainda calcula (N>=2)
    assert not cal.sufficient             # mas não autoriza recalibrar
    assert cal.n < MIN_N
    assert "insuficiente" in calibration_markdown(cal).lower()


def test_weak_signal_verdict_blocks_recalibration():
    # Espelha o resultado REAL (N grande, correlações fracas/negativas).
    cal = Calibration(n=143, n_total=176, fitness=-0.22,
                      by_component={"Personagem": -0.18, "Raridade": 0.06,
                                    "Supply": -0.24, "Preço": -0.06},
                      mean_trend=-0.9)
    assert cal.sufficient                       # N alto, mas...
    md = calibration_markdown(cal, "CardMarket").lower()
    assert "não recalibrar" in md and "sinal fraco" in md
    assert "momentum" in md                     # avisa do risco de fitar curto prazo


def test_strong_signal_verdict_allows_cautious_adjust():
    cal = Calibration(n=50, n_total=60, fitness=0.40,
                      by_component={"Personagem": 0.45, "Raridade": 0.10,
                                    "Supply": 0.30, "Preço": 0.05},
                      mean_trend=2.0)
    md = calibration_markdown(cal, "CardMarket").lower()
    assert "cautela" in md and "sinal fraco" not in md


def test_none_trends_count_only_in_total():
    pairs = ([(_sc(char=i), None) for i in range(5)]
             + [(_sc(char=i), float(i)) for i in range(1, 13)])
    cal = calibrate(pairs)
    assert cal.n == 12 and cal.n_total == 17
    assert cal.coverage == pytest.approx(12 / 17)


def test_all_none_is_safe():
    cal = calibrate([(_sc(), None), (_sc(), None)])
    assert cal.n == 0 and cal.fitness is None and not cal.sufficient


def test_cardmarket_trend_pct_ground_truth():
    up = {"cardmarket": {"prices": {"avg7": 110.0, "avg30": 100.0}}}
    down = {"cardmarket": {"prices": {"avg7": 90.0, "avg30": 100.0}}}
    assert cardmarket_trend_pct(up) == pytest.approx(10.0)
    assert cardmarket_trend_pct(down) == pytest.approx(-10.0)
    # faltando dado / avg30<=0 / sem bloco -> None (nunca inventa)
    assert cardmarket_trend_pct({"cardmarket": {"prices": {"avg7": 5}}}) is None
    assert cardmarket_trend_pct(
        {"cardmarket": {"prices": {"avg7": 5, "avg30": 0}}}) is None
    assert cardmarket_trend_pct({}) is None


def test_evaluator_payload_contract():
    pairs = [(_sc(char=i, rar=i, sup=i, pri=i), float(i)) for i in range(1, 13)]
    pl = evaluator_payload(calibrate(pairs))
    assert pl["score"] == pytest.approx(1.0)
    assert pl["metrics"]["n"] == 12
    assert pl["metrics"]["sufficient"] is True
    assert "spearman_personagem" in pl["metrics"]
    # sem amostra -> score 0.0 (ASI-Evolve nunca recebe None)
    assert evaluator_payload(calibrate([(_sc(), None)]))["score"] == 0.0
