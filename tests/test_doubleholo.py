"""Testes da coluna DH (2ª opinião Double Holo) — load, join e render.

A fórmula `dh_score` é single-source no pipeline (scanners-commons); a cobertura
dela vive em `tooling/test_doubleholo_signals.py`. Aqui o outlook só LÊ o
`dh_score` precomputado do JSON canônico.
"""
import json
from datetime import date

from outlook.doubleholo import attach_scores, load_signals
from outlook.report import ranking_markdown
from outlook.scoring import ScoredCard


def _rec(pid, dh, **sig):
    return {"tcg_product_id": pid, "dh_score": dh, "signals": sig}


def test_load_signals_keys_by_product_id_and_skips_missing(tmp_path):
    data = [
        {"tcg_product_id": "111", "dh_score": 70, "signals": {}},
        {"tcg_product_id": None, "dh_score": 70, "signals": {}},  # sem pid -> ignora
        {"dh_score": 50, "signals": {}},                          # idem
    ]
    p = tmp_path / "dh.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    sigs = load_signals(str(p))
    assert set(sigs) == {"111"}


def test_load_signals_accepts_single_record(tmp_path):
    p = tmp_path / "one.json"
    p.write_text(json.dumps({"tcg_product_id": "999", "dh_score": 60, "signals": {}}), encoding="utf-8")
    assert set(load_signals(str(p))) == {"999"}


def _card(card_id):
    return ScoredCard(card_id=card_id, name="X", set_name="S", set_id="s1",
                      number="1", rarity="?", series="Z", release=date(2024, 1, 1),
                      market_usd=10.0)


def test_attach_scores_reads_precomputed_by_card_id():
    cards = [_card("111"), _card("222")]
    sigs = {"111": _rec("111", 70)}  # só 111 tem dado
    n = attach_scores(cards, sigs)
    assert n == 1
    assert cards[0].dh_score == 70    # lê o precomputado, NÃO recalcula
    assert cards[1].dh_score is None  # sem dado -> None (coluna mostra "—")


def test_attach_scores_matched_record_without_dh_score_is_none():
    # registro casado mas sem o campo (JSON antigo) -> None, não inventa nota.
    cards = [_card("111")]
    sigs = {"111": {"tcg_product_id": "111", "signals": {"forecast_dir": "buy"}}}
    n = attach_scores(cards, sigs)
    assert n == 1
    assert cards[0].dh_score is None


def test_ranking_hides_dh_column_by_default():
    md = ranking_markdown([_card("1")], top_n=5)
    assert "DH" not in md.split("\n")[2]  # cabeçalho da tabela sem DH


def test_ranking_shows_dh_column_when_requested():
    c = _card("1")
    c.dh_score = 70
    md = ranking_markdown([c], top_n=5, show_dh=True)
    header = [ln for ln in md.split("\n") if ln.startswith("| #")][0]
    assert "DH" in header
    assert "| 70 |" in md  # célula do score DH renderizada


def test_ranking_dh_score_zero_renders_zero_not_dash():
    # 0 é uma nota VÁLIDA — não pode virar "—" (conflação falsy).
    c = _card("1")
    c.dh_score = 0
    md = ranking_markdown([c], top_n=5, show_dh=True)
    assert "| 0 |" in md
