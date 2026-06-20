"""Calibração do score de longo prazo — fecha o loop contra preço realizado.

Baixa o catálogo da pokemontcg.io, pontua cada carta (preço TCGPlayer) e mede a
correlação (Spearman) entre o score — e cada componente — e a TENDÊNCIA REALIZADA
de cada carta no CardMarket (média 7d vs 30d). É a função de fitness do
ASI-Evolve e o juiz honesto de "as respostas estão mais precisas?".

Por que CardMarket: a tendência (avg7 vs avg30) vem direto da API oficial, por
carta, sem scraping — robusto e de graça. É curto prazo (ressalva de sempre),
mas é movimento de mercado REAL, não inventado.

Uso:
  python run_evaluate.py                                  # SV+SWSH+ME
  python run_evaluate.py --eras "Scarlet & Violet" --max-sets 6
  python run_evaluate.py --dump experiments/longterm_score/dataset.json

A entrega é a TABELA no chat (regra do projeto). O --dump grava o dataset
(inputs + ground truth) que o experimento ASI-Evolve usa pra evoluir o scorer.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from outlook import ptcg_api
from outlook.evaluate import calibrate, calibration_markdown
from outlook.scoring import score_card

DEFAULT_ERAS = ["Scarlet & Violet", "Sword & Shield", "Mega Evolution"]


def _stratified(rows: list, sample: int) -> list:
    """`sample` cartas espalhadas pela faixa de score (variância importa)."""
    if sample <= 0 or len(rows) <= sample:
        return rows
    ranked = sorted(rows, key=lambda r: r[0].score)
    step = len(ranked) / sample
    return [ranked[int(i * step)] for i in range(sample)]


def main() -> int:
    ap = argparse.ArgumentParser(description="Calibração score × preço realizado (CardMarket)")
    ap.add_argument("--eras", nargs="*", default=DEFAULT_ERAS)
    ap.add_argument("--min-price", type=float, default=15.0,
                    help="preço TCGPlayer mínimo US$ (default 15)")
    ap.add_argument("--max-price", type=float, default=1000.0)
    ap.add_argument("--max-sets", type=int, default=0,
                    help="limita aos N sets mais recentes por era (0 = todos)")
    ap.add_argument("--sample", type=int, default=0,
                    help="limita o dataset a N cartas espalhadas (0 = todas)")
    ap.add_argument("--dump", type=str, default="",
                    help="grava dataset.json (inputs + ground truth) p/ ASI-Evolve")
    args = ap.parse_args()

    print(f"Fonte: pokemontcg.io | Eras: {args.eras}", file=sys.stderr)
    sets_meta = ptcg_api.fetch_sets(args.eras)
    if args.max_sets > 0:
        sets_meta = sorted(sets_meta, key=lambda s: s.get("releaseDate", ""),
                           reverse=True)[:args.max_sets]
    print(f"{len(sets_meta)} sets; baixando cartas...", file=sys.stderr)

    rows, no_trend = [], 0
    for i, s in enumerate(sets_meta, 1):
        n_set = 0
        for card in ptcg_api.fetch_cards_for_set(s["id"]):
            usd = ptcg_api.best_market_usd(card)
            if usd is None or not (args.min_price <= usd <= args.max_price):
                continue
            trend = ptcg_api.cardmarket_trend_pct(card)
            if trend is None:
                no_trend += 1
            rows.append((score_card(card, s, usd), card, s, usd, trend))
            n_set += 1
        print(f"  [{i}/{len(sets_meta)}] {s['name']}: {n_set} cartas premium",
              file=sys.stderr)
    if not rows:
        print("Universo vazio — confira eras/filtros.", file=sys.stderr)
        return 1

    rows = _stratified(rows, args.sample)
    pairs = [(sc, trend) for sc, _, _, _, trend in rows]
    cal = calibrate(pairs)

    md = (f"# Calibração — {datetime.now():%Y-%m-%d}\n\n"
          + calibration_markdown(cal, "pokemontcg.io + CardMarket (avg7/avg30)"))
    print(md)

    if args.dump:
        dataset = [{
            "card": {"id": c.get("id", ""), "name": c.get("name", ""),
                     "number": c.get("number", ""),
                     "rarity": c.get("rarity", "") or "?"},
            "set_meta": {"id": sm.get("id", ""), "name": sm.get("name", ""),
                         "releaseDate": sm.get("releaseDate", ""),
                         "series": sm.get("series", "")},
            "market_usd": usd, "trend_pct": trend,
        } for _, c, sm, usd, trend in rows]
        out = Path(args.dump)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(dataset, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print(f"\n(dataset ASI-Evolve: {out} — {len(dataset)} linhas, "
              f"{sum(1 for r in dataset if r['trend_pct'] is not None)} com trend)",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
