"""Avaliador de cenário Pokémon TCG + score de longo prazo — CLI.

O que ele faz, em uma frase: baixa o catálogo das eras escolhidas no
pokemontcg.io (raridades, datas, preços TCGPlayer do dia), dá um score de
potencial de LONGO PRAZO 0-100 pra cada carta premium (4 componentes com
racional aberto) e imprime: (1) um panorama do cenário por era e (2) a
tabela top-N ranqueada.

Uso típico:
  python run_outlook.py                          # eras SV + SWSH, top 50
  python run_outlook.py --top 30 --trend         # + tendência PriceCharting no top
  python run_outlook.py --eras "Scarlet & Violet" --min-price 20

Este avaliador NUNCA decide compra. Score alto = "olhe primeiro", não
"compre". Decisão de capital é do operador.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from outlook import ptcg_api, tcgcsv_api
from outlook.pricecharting import fetch_trend
from outlook.report import ranking_markdown, scenario_markdown
from outlook.scoring import score_card

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "outputs"

DEFAULT_ERAS = ["Scarlet & Violet", "Sword & Shield", "Mega Evolution"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Cenário Pokémon TCG + score de longo prazo")
    ap.add_argument("--eras", nargs="*", default=DEFAULT_ERAS,
                    help=f"séries pokemontcg.io (default: {DEFAULT_ERAS})")
    ap.add_argument("--top", type=int, default=50, help="linhas no ranking (default 50)")
    ap.add_argument("--min-price", type=float, default=5.0,
                    help="preço market mínimo US$ pra entrar na análise (default 5)")
    ap.add_argument("--max-price", type=float, default=1000.0,
                    help="preço market máximo US$ (default 1000 — acima já está precificado)")
    ap.add_argument("--trend", action="store_true",
                    help="busca tendência no PriceCharting pro top-N (lento, ~2s/carta)")
    ap.add_argument("--source", choices=["tcgcsv", "ptcg"], default="tcgcsv",
                    help="tcgcsv (default; dumps diários TCGPlayer, estável) "
                         "ou ptcg (pokemontcg.io ao vivo, oscila)")
    args = ap.parse_args()

    api = tcgcsv_api if args.source == "tcgcsv" else ptcg_api
    print(f"Fonte: {args.source} | Eras: {args.eras}")
    sets_meta = api.fetch_sets(args.eras)
    print(f"{len(sets_meta)} sets encontrados; baixando cartas (pode levar ~1-2 min)...")

    scored, skipped_no_price = [], 0
    for i, s in enumerate(sets_meta, 1):
        if args.source == "tcgcsv":
            cards = tcgcsv_api.fetch_cards_with_prices(s["id"])
        else:
            cards = ptcg_api.fetch_cards_for_set(s["id"])
        n_set = 0
        for card in cards:
            usd = api.best_market_usd(card)
            if usd is None:
                skipped_no_price += 1
                continue
            if not (args.min_price <= usd <= args.max_price):
                continue
            sc = score_card(card, s, usd)
            sc.tcg_url = api.tcgplayer_url(card)
            scored.append(sc)
            n_set += 1
        print(f"  [{i}/{len(sets_meta)}] {s['name']}: {n_set} cartas no universo")

    if not scored:
        print("Nenhuma carta no universo — confira eras/filtros.")
        return 1

    if args.trend:
        ranked = sorted(scored, key=lambda c: (-c.score, -c.market_usd))[:args.top]
        print(f"Buscando tendência PriceCharting pro top {len(ranked)} (best-effort)...")
        for c in ranked:
            c.trend = fetch_trend(c.name, c.set_name, c.number)
            time.sleep(1.5)

    md = (f"# Cenário Pokémon TCG + score de longo prazo — "
          f"{datetime.now():%Y-%m-%d}\n\n"
          + scenario_markdown(scored, sets_meta, skipped_no_price, args.source)
          + "\n\n" + ranking_markdown(scored, args.top))
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"outlook_{datetime.now():%Y%m%d_%H%M%S}.md"
    out.write_text(md, encoding="utf-8")
    print()
    print(md)
    print(f"\n(apoio local: {out} — a entrega oficial é a tabela acima, no chat)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
