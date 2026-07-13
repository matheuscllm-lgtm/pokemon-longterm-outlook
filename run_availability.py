"""Onde cada carta do top-N está mais barata em NM inglês — CLI.

Recalcula o ranking (fonte tcgcsv, mesma régua do run_outlook) e, pra cada
carta do top-N:
  - consulta o CardTrader AO VIVO (menor oferta EN+NM não-graded, preço real;
    exige CT_JWT — env var ou .env do card-trader-scanner no PC);
  - mostra a referência TCGPlayer (market) e o menor anúncio TCGPlayer
    (lowPrice — condição NÃO filtrada, informativo);
  - monta links diretos de eBay / COMC / Liga / MYP (busca — essas
    plataformas não têm preço automatizável barato hoje; ver availability.py).

O veredito "mais barato NM-EN" SÓ compara fontes com filtro NM+EN real
(hoje: CardTrader) contra a referência market do TCGPlayer — o lowPrice
nunca decide, porque não é NM garantido.

Uso:
  python run_availability.py --top 100
  python run_availability.py --top 50 --eras "Scarlet & Violet"

Decisão de compra é do operador; isto aqui só coleta e linka.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from outlook import tcgcsv_api
from outlook.availability import (CTAvailability, comc_url, ebay_url,
                                  liga_url, load_ct_jwt, myp_url)
from outlook.scoring import score_card

HERE = Path(__file__).resolve().parent
DEFAULT_ERAS = ["Scarlet & Violet", "Sword & Shield", "Mega Evolution"]


def collect_top(eras: list[str], min_price: float, max_price: float,
                top_n: int) -> list:
    sets_meta = tcgcsv_api.fetch_sets(eras)
    scored = []
    for i, s in enumerate(sets_meta, 1):
        for card in tcgcsv_api.fetch_cards_with_prices(s["id"]):
            usd = tcgcsv_api.best_market_usd(card)
            if usd is None or not (min_price <= usd <= max_price):
                continue
            sc = score_card(card, s, usd)
            sc.tcg_url = tcgcsv_api.tcgplayer_url(card)
            sc.low_usd = tcgcsv_api.best_low_usd(card)
            scored.append(sc)
        print(f"  [{i}/{len(sets_meta)}] {s['name']}", file=sys.stderr)
    return sorted(scored, key=lambda c: (-c.score, -c.market_usd))[:top_n]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Onde cada carta do top está acessível (preço CT real + links)")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--eras", nargs="*", default=DEFAULT_ERAS)
    ap.add_argument("--min-price", type=float, default=5.0)
    ap.add_argument("--max-price", type=float, default=1000.0)
    args = ap.parse_args()

    jwt = load_ct_jwt()
    if not jwt:
        print("⚠️ CT_JWT ausente (env var CT_JWT ou .env do card-trader-scanner) "
              "— CardTrader sai sem preço (só links) e o veredito NM-EN vira n/d.")
    ct = CTAvailability(jwt) if jwt else None

    print("Recalculando ranking (tcgcsv)...", file=sys.stderr)
    top = collect_top(args.eras, args.min_price, args.max_price, args.top)

    lines = [f"# Onde está mais barata (NM inglês) — top {len(top)} "
             f"({datetime.now():%Y-%m-%d %H:%M})", ""]
    lines.append("| # | Score | Carta | Set | Nº | TCG market US$ (ref) | "
                 "TCG low US$* | CT NM-EN US$ | Qtd CT | Mais barato NM-EN | "
                 "Links |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for i, c in enumerate(top, 1):
        if ct:
            print(f"[{i}/{len(top)}] CT lookup: {c.name} ({c.set_name} {c.number})",
                  file=sys.stderr)
            r = ct.cheapest(c.set_name, c.number)
        else:
            r = {"status": "sem CT_JWT"}
        ct_usd = r.get("usd")
        ct_cell = f"{ct_usd:.2f}" if ct_usd is not None else f"— ({r['status']})"
        qty = r.get("qty") if r.get("qty") is not None else "—"
        low_cell = f"{c.low_usd:.2f}" if c.low_usd is not None else "—"
        if ct_usd is not None:
            delta = abs(ct_usd - c.market_usd) / c.market_usd * 100
            if ct_usd < c.market_usd:
                verdict = (f"**CardTrader** US$ {ct_usd:.2f} "
                           f"({delta:.0f}% abaixo da ref TCG)")
            else:
                verdict = (f"**TCGPlayer** (ref; CT está {delta:.0f}% acima)")
        elif ct:
            verdict = f"n/d — CT: {r['status']}; confira os links"
        else:
            verdict = "n/d — sem fonte NM-EN ao vivo (defina CT_JWT)"
        links = []
        if r.get("url"):
            links.append(f"[CT]({r['url']})")
        links.append(f"[TCG]({c.tcg_url})")
        links.append(f"[eBay]({ebay_url(c.name, c.set_name, c.number)})")
        links.append(f"[COMC]({comc_url(c.name)})")
        links.append(f"[Liga]({liga_url(c.name)})")
        links.append(f"[MYP]({myp_url(c.name)})")
        lines.append(f"| {i} | {c.score} | {c.name.replace('|', ' ')} | "
                     f"{c.set_name.replace('|', ' ')} | {c.number} | "
                     f"{c.market_usd:.2f} | {low_cell} | {ct_cell} | {qty} | "
                     f"{verdict} | {' · '.join(links)} |")
    lines.append("")
    lines.append("_CT NM-EN US$ = menor oferta EN + Near Mint não-graded ao "
                 "vivo na API do CardTrader (convertida pra US$; token CT_JWT "
                 "via env var ou .env do card-trader-scanner). TCG low* = menor "
                 "anúncio atual no TCGPlayer, condição NÃO filtrada (pode ser "
                 "LP/HP) — informativo, nunca decide o veredito NM-EN. O "
                 "veredito compara o anúncio NM-EN coletado com a referência "
                 "market do TCGPlayer (média de vendas, não é anúncio). "
                 "eBay/COMC/Liga/MYP: sem preço automatizado (MYP: API atrás de "
                 "Cloudflare — ver availability.py) — links de busca pra "
                 "conferência manual. Decisão é do operador._")
    md = "\n".join(lines)
    out = HERE / "outputs" / f"availability_{datetime.now():%Y%m%d_%H%M%S}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print()
    print(md)
    print(f"\n(apoio local: {out})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
