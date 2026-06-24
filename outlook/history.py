"""Persistência de snapshots diários — a memória que faltava à ferramenta.

A fonte tcgcsv é um dump DIÁRIO; até aqui cada run descartava o dado. Salvar
cada run num CSV datado constrói uma SÉRIE HISTÓRICA própria — o eixo do tempo
que um outlook de longo prazo precisa. Destrava:
  - tendência REAL (Δ de preço entre datas), não as ~6 vendas do PriceCharting;
  - o backtest do score (outlook/validate.py): score alto de fato subiu mais?

Formato: data/snapshots/snapshot_YYYY-MM-DD.csv (1 arquivo por dia, idempotente
— rodar 2x no mesmo dia sobrescreve). Sem dependências: csv da stdlib. Os CSVs
NÃO entram no git (.gitignore) — são dados do operador, crescem por dia.

CLI: `python -m outlook.history` resume a história (dias, range, maiores
altas/quedas entre o 1º e o último snapshot).
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Iterable

from .scoring import ScoredCard

HERE = Path(__file__).resolve().parent.parent
SNAP_DIR = HERE / "data" / "snapshots"

FIELDS = [
    "date", "source", "card_id", "set_id", "set_name", "number", "name",
    "rarity", "series", "release", "market_usd", "notorious", "heavy_reprint",
    "score", "pts_character", "pts_rarity", "pts_supply", "pts_price",
]


def snapshot_path(when: date) -> Path:
    return SNAP_DIR / f"snapshot_{when:%Y-%m-%d}.csv"


def save_snapshot(cards: Iterable[ScoredCard], source: str = "tcgcsv",
                  when: date | None = None) -> Path:
    """Grava o universo pontuado num CSV datado. Devolve o caminho."""
    when = when or date.today()
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    path = snapshot_path(when)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for c in cards:
            w.writerow({
                "date": when.isoformat(), "source": source,
                "card_id": c.card_id, "set_id": c.set_id,
                "set_name": c.set_name, "number": c.number, "name": c.name,
                "rarity": c.rarity, "series": c.series,
                "release": c.release.isoformat(),
                "market_usd": f"{c.market_usd:.2f}",
                "notorious": c.notorious or "",
                "heavy_reprint": int(c.heavy_reprint),
                "score": c.score, "pts_character": c.pts_character,
                "pts_rarity": c.pts_rarity, "pts_supply": c.pts_supply,
                "pts_price": c.pts_price,
            })
    return path


def list_snapshots() -> list[Path]:
    if not SNAP_DIR.exists():
        return []
    return sorted(SNAP_DIR.glob("snapshot_*.csv"))


def load_rows() -> list[dict]:
    rows: list[dict] = []
    for p in list_snapshots():
        with p.open(newline="", encoding="utf-8") as fh:
            rows.extend(csv.DictReader(fh))
    return rows


def card_series(card_id: str) -> list[tuple[date, float, int]]:
    """(data, market_usd, score) ordenado por data, para um card_id."""
    out: list[tuple[date, float, int]] = []
    for r in load_rows():
        if r["card_id"] == card_id:
            out.append((date.fromisoformat(r["date"]),
                        float(r["market_usd"]), int(r["score"])))
    return sorted(out)


def price_change(card_id: str) -> tuple[float, int] | None:
    """(% mudança, dias) entre o 1º e o último snapshot do card. None se <2."""
    s = card_series(card_id)
    if len(s) < 2:
        return None
    (d0, p0, _), (d1, p1, _) = s[0], s[-1]
    if p0 <= 0:
        return None
    return (100.0 * (p1 - p0) / p0, (d1 - d0).days)


def summary() -> str:
    snaps = list_snapshots()
    if not snaps:
        return ("Nenhum snapshot ainda. Rode run_outlook.py — cada run salva 1 "
                "snapshot e a tendência real começa a existir a partir do 2º dia.")
    rows = load_rows()
    dates = sorted({r["date"] for r in rows})
    lines = [f"Snapshots: {len(snaps)} dia(s) ({dates[0]} → {dates[-1]}); "
             f"{len(rows)} linhas-carta no total."]
    if len(dates) < 2:
        lines.append("(só 1 dia de dados — rode em outra data p/ ter tendência.)")
        return "\n".join(lines)
    moves, seen = [], set()
    for r in rows:
        cid = r["card_id"]
        if cid in seen:
            continue
        seen.add(cid)
        ch = price_change(cid)
        if ch:
            moves.append((ch[0], r["name"], r["set_name"], ch[1]))
    moves.sort(reverse=True)
    lines.append("\nMaiores altas (1º→último snapshot):")
    for pct, nm, st, days in moves[:10]:
        lines.append(f"  {pct:+6.1f}%  {nm} ({st})  em {days}d")
    lines.append("Maiores quedas:")
    for pct, nm, st, days in sorted(moves)[:10]:
        lines.append(f"  {pct:+6.1f}%  {nm} ({st})  em {days}d")
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary())
