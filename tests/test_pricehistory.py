"""Testes do histórico de preço (tcgcsv) — lógica pura, SEM rede.

A parte cara (download + descompressão PPMd) não é exercida aqui; testamos as
funções determinísticas: seleção de datas, parsing/exclusão de reverse, cálculo
da tendência e os caminhos honestos de "n/d". Um round-trip real de `.7z` roda
só se o `py7zr` suportar escrita no ambiente (senão é pulado).
"""
import json
from datetime import date
from pathlib import Path

import pytest

from outlook import pricehistory as ph
from outlook.pricehistory import (Trend, _best_market_from_rows, _label,
                                  _map_from_extracted, target_dates, trend_for)

TODAY = date(2026, 6, 22)


# --------------------------------------------------------------------------- #
# Datas de referência
# --------------------------------------------------------------------------- #
def test_target_dates_basic_windows():
    td = target_dates(TODAY, windows=(30, 90, 180, 365))
    assert td[30] == date(2026, 5, 23)
    assert td[365] == date(2025, 6, 22)
    assert set(td) == {30, 90, 180, 365}


def test_target_dates_clamps_before_earliest():
    # Janela que cairia antes de 2024-02-08 é descartada (não há arquivo).
    near = date(2024, 3, 1)
    td = target_dates(near, windows=(7, 365))
    assert 7 in td               # 2024-02-23, depois do início
    assert 365 not in td         # 2023-03 — antes do arquivo


def test_target_dates_excludes_future_and_today():
    td = target_dates(TODAY, windows=(0,))
    assert td == {}              # "hoje" não é ponto histórico


# --------------------------------------------------------------------------- #
# Parsing de preço (mesma regra do live: ignora reverse, pega o maior market)
# --------------------------------------------------------------------------- #
def test_best_market_excludes_reverse_and_takes_max():
    rows = [
        {"productId": 5, "subTypeName": "Normal", "marketPrice": 10.0},
        {"productId": 5, "subTypeName": "Holofoil", "marketPrice": 25.0},
        {"productId": 5, "subTypeName": "Reverse Holofoil", "marketPrice": 999.0},
        {"productId": 6, "subTypeName": "Holofoil", "marketPrice": 4.0},
        {"productId": 7, "subTypeName": "Normal", "marketPrice": None},
        {"productId": 8, "subTypeName": "Normal", "marketPrice": 0},
    ]
    out = _best_market_from_rows(rows)
    assert out["5"] == 25.0       # maior não-reverse (reverse 999 ignorado)
    assert out["6"] == 4.0
    assert "7" not in out and "8" not in out   # None/0 não entram


def test_map_from_extracted_filters_category_3(tmp_path: Path):
    # Estrutura real do arquivo: <data>/<categoria>/<grupo>/prices
    p3 = tmp_path / "2024-02-08" / "3" / "999" / "prices"
    p3.parent.mkdir(parents=True)
    p3.write_text(json.dumps({"results": [
        {"productId": 100, "subTypeName": "Normal", "marketPrice": 12.5},
        {"productId": 100, "subTypeName": "Reverse Holofoil", "marketPrice": 50},
    ]}))
    # Categoria 1, grupo 3 — NÃO é Pokémon; precisa ser excluída.
    p1 = tmp_path / "2024-02-08" / "1" / "3" / "prices"
    p1.parent.mkdir(parents=True)
    p1.write_text(json.dumps({"results": [
        {"productId": 777, "subTypeName": "Normal", "marketPrice": 8.0},
    ]}))
    out = _map_from_extracted(tmp_path)
    assert out == {"100": 12.5}   # só a categoria 3, sem o reverse


# --------------------------------------------------------------------------- #
# Cálculo de tendência
# --------------------------------------------------------------------------- #
def test_label_thresholds():
    assert _label(20.0, "1a").startswith("↑")
    assert _label(-20.0, "1a").startswith("↓")
    assert _label(3.0, "1a").startswith("→")     # dentro de ±8% = estável
    assert _label(None, "1a") == "n/d"


def test_trend_uses_longest_available_window():
    maps = {
        90: {"100": 80.0},
        365: {"100": 50.0},        # 1 ano atrás custava 50; hoje 100 = +100%
    }
    t = trend_for("100", today_price=100.0, maps=maps)
    assert t.horizon_long == "1a"  # headline usa a MAIOR janela disponível
    assert round(t.pct_long) == 100
    assert t.label.startswith("↑ +100% (1a)")
    assert round(t.pct_recent) == 25   # momentum 90d: 80→100 = +25%


def test_trend_falls_back_to_shorter_window_when_no_long_history():
    # Carta de set novo: o productId só existe no ponto de 30d (365d tem outro).
    maps = {30: {"100": 90.0}, 365: {"200": 10.0}}
    t = trend_for("100", today_price=108.0, maps=maps)   # 90 → 108 = +20%
    assert t.horizon_long == "1m"            # caiu na única janela com o produto
    assert t.label.startswith("↑ +20% (1m)")
    assert t.pct_recent is None              # sem ponto de 90d pra esse produto


def test_trend_nd_when_product_absent():
    maps = {365: {"999": 10.0}}
    t = trend_for("100", today_price=50.0, maps=maps)
    assert t.label == "n/d (sem histórico)"
    assert t.pct_long is None


def test_trend_nd_when_no_maps():
    assert trend_for("100", 50.0, maps={}).label == "n/d (sem histórico)"


# --------------------------------------------------------------------------- #
# Round-trip real de .7z (best-effort — pulado se py7zr não escrever)
# --------------------------------------------------------------------------- #
def test_extract_cat3_roundtrip(tmp_path: Path):
    py7zr = pytest.importorskip("py7zr")
    # Monta a árvore como no arquivo real e compacta num .7z.
    root = tmp_path / "tree"
    pricefile = root / "2024-02-08" / "3" / "999" / "prices"
    pricefile.parent.mkdir(parents=True)
    pricefile.write_text(json.dumps({"results": [
        {"productId": 42, "subTypeName": "Holofoil", "marketPrice": 7.0},
    ]}))
    archive = tmp_path / "snap.7z"
    try:
        with py7zr.SevenZipFile(archive, "w") as z:
            z.writeall(str(root), arcname="")
    except Exception as exc:                       # escrita não suportada
        pytest.skip(f"py7zr sem escrita neste ambiente: {exc}")
    out = ph._extract_cat3_map(archive)
    assert out == {"42": 7.0}


def test_py7zr_available_is_bool():
    assert isinstance(ph.py7zr_available(), bool)


# --------------------------------------------------------------------------- #
# Robustez: nunca estoura a run (contrato "degrada pra n/d")
# --------------------------------------------------------------------------- #
def test_download_rejects_non_7z_body(tmp_path, monkeypatch):
    """Um corpo HTML servido como 200 (challenge CF) NÃO vira cache envenenado."""
    monkeypatch.setattr(ph, "CACHE_DIR", tmp_path)

    class _Resp:
        status_code = 200
        content = b"<html>cloudflare challenge</html>"

    monkeypatch.setattr(ph.requests, "get", lambda *a, **k: _Resp())
    assert ph._download(date(2024, 2, 8)) is None
    assert list(tmp_path.glob("*.7z")) == []     # nada gravado no cache


def test_price_map_degrades_on_corrupt_archive(tmp_path, monkeypatch):
    """7z corrompido/truncado -> None (sem estourar) e o cache envenenado some."""
    pytest.importorskip("py7zr")
    monkeypatch.setattr(ph, "CACHE_DIR", tmp_path)
    garbage = tmp_path / "prices-2024-02-08.ppmd.7z"
    garbage.write_bytes(ph.MAGIC_7Z + b"corpo invalido, nao e um 7z de verdade")
    monkeypatch.setattr(
        ph, "_download", lambda d: garbage if d == date(2024, 2, 8) else None
    )
    # NÃO pode levantar; degrada pra None; remove o arquivo envenenado.
    assert ph.price_map_for_date(date(2024, 2, 8)) is None
    assert not garbage.exists()
