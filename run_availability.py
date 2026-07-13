"""Onde cada carta do top-N está mais barata em NM inglês — CLI.

Recalcula o ranking (fonte tcgcsv, mesma régua do run_outlook) e, pra cada
carta do top-N:
  - consulta o CardTrader AO VIVO (menor oferta EN+NM não-graded, preço real;
    exige CT_JWT — env var ou .env do card-trader-scanner no PC);
  - mostra a referência TCGPlayer (market) e o menor anúncio TCGPlayer
    (lowPrice — condição NÃO filtrada, informativo);
  - consulta o eBay AO VIVO (menor anúncio ativo plausível, Browse API —
    exige EBAY_CLIENT_ID/SECRET; sem elas, só link) — informativo;
  - opcionalmente consulta a COMC (menor listagem EX-NM ungraded EN, via
    Firecrawl — OPT-IN --comc-price, consome créditos pagos) — informativo;
  - monta links diretos de eBay / COMC / Liga / MYP (busca — Liga/MYP não
    têm preço automatizável barato hoje; ver availability.py).

O veredito "mais barato NM-EN" SÓ compara fontes com filtro NM+EN real
(hoje: CardTrader) contra a referência market do TCGPlayer — TCG low, eBay
e COMC nunca decidem: são match por busca/condição não-estrita (ver
rodapé do relatório).

Uso:
  python run_availability.py --top 100
  python run_availability.py --top 50 --eras "Scarlet & Violet"
  python run_availability.py --top 25 --comc-price   # + COMC (créditos)

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
                                  liga_url, load_ct_jwt, myp_url,
                                  verdict_nm_en)
from outlook.comc_availability import COMCAvailability, load_firecrawl_key
from outlook.ebay_availability import EbayAvailability, load_ebay_keys
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
    ap.add_argument("--no-ebay", action="store_true",
                    help="pula o preço eBay mesmo com EBAY_CLIENT_ID/SECRET")
    ap.add_argument("--comc-price", action="store_true",
                    help="coleta preço COMC via Firecrawl (OPT-IN: consome "
                         "créditos pagos — ~1 fetch por carta; exige "
                         "FIRECRAWL_API_KEY)")
    args = ap.parse_args()

    jwt = load_ct_jwt()
    if not jwt:
        print("⚠️ CT_JWT ausente (env var CT_JWT ou .env do card-trader-scanner) "
              "— CardTrader sai sem preço (só links) e o veredito NM-EN vira n/d.")
    ct = CTAvailability(jwt) if jwt else None

    ebay = None
    if not args.no_ebay:
        keys = load_ebay_keys()
        if keys:
            ebay = EbayAvailability(*keys)
        else:
            print("ℹ️ EBAY_CLIENT_ID/SECRET ausentes — eBay sai só como link "
                  "de busca (sem preço).")
    comc = None
    if args.comc_price:
        fk = load_firecrawl_key()
        if fk:
            comc = COMCAvailability(fk)
            print("⚠️ --comc-price: cada carta = 1 fetch Firecrawl (créditos "
                  "pagos).", file=sys.stderr)
        else:
            print("⚠️ --comc-price pedido mas FIRECRAWL_API_KEY ausente — "
                  "COMC sai só como link de busca (sem preço).")

    print("Recalculando ranking (tcgcsv)...", file=sys.stderr)
    top = collect_top(args.eras, args.min_price, args.max_price, args.top)

    lines = [f"# Onde está mais barata (NM inglês) — top {len(top)} "
             f"({datetime.now():%Y-%m-%d %H:%M})", ""]
    lines.append("| # | Score | Carta | Set | Nº | TCG market US$ (ref) | "
                 "TCG low US$* | CT NM-EN US$ | Qtd CT | eBay US$* | "
                 "COMC US$* | Mais barato NM-EN | Links |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")

    def price_cell(r: dict) -> str:
        usd = r.get("usd")
        if usd is None:
            return f"— ({r['status']})"
        cell = f"{usd:.2f}"
        if r.get("junk_skipped"):
            cell += f" ({r['junk_skipped']} lixo ign.)"
        return cell

    for i, c in enumerate(top, 1):
        if ct:
            print(f"[{i}/{len(top)}] CT lookup: {c.name} ({c.set_name} {c.number})",
                  file=sys.stderr)
            r = ct.cheapest(c.set_name, c.number, c.name, ref_usd=c.market_usd)
        else:
            r = {"status": "sem CT_JWT"}
        ct_usd = r.get("usd")
        ct_cell = price_cell(r) if ct else "— (sem CT_JWT)"
        qty = r.get("qty") if r.get("qty") is not None else "—"
        low_cell = f"{c.low_usd:.2f}" if c.low_usd is not None else "—"
        if ebay:
            re_ = ebay.cheapest(c.name, c.set_name, c.number,
                                ref_usd=c.market_usd)
            ebay_cell = price_cell(re_)
        else:
            re_, ebay_cell = {}, "—"
        if comc:
            rc = comc.cheapest(c.name, c.number, ref_usd=c.market_usd)
            comc_cell = price_cell(rc)
        else:
            rc, comc_cell = {}, "—"
        verdict = verdict_nm_en(ct_usd, c.market_usd,
                                ct_status=r.get("status", ""), has_ct=bool(ct))
        links = []
        if r.get("url"):
            links.append(f"[CT]({r['url']})")
        links.append(f"[TCG]({c.tcg_url})")
        links.append(f"[eBay]({re_.get('url') or ebay_url(c.name, c.set_name, c.number)})")
        links.append(f"[COMC]({rc.get('url') or comc_url(c.name)})")
        links.append(f"[Liga]({liga_url(c.name)})")
        links.append(f"[MYP]({myp_url(c.name)})")
        lines.append(f"| {i} | {c.score} | {c.name.replace('|', ' ')} | "
                     f"{c.set_name.replace('|', ' ')} | {c.number} | "
                     f"{c.market_usd:.2f} | {low_cell} | {ct_cell} | {qty} | "
                     f"{ebay_cell} | {comc_cell} | "
                     f"{verdict} | {' · '.join(links)} |")
    lines.append("")
    lines.append("_CT NM-EN US$ = menor oferta EN + Near Mint não-graded ao "
                 "vivo na API do CardTrader (convertida pra US$; token CT_JWT "
                 "via env var ou .env do card-trader-scanner). TCG low* = menor "
                 "anúncio atual no TCGPlayer, condição NÃO filtrada (pode ser "
                 "LP/HP) — informativo, nunca decide o veredito NM-EN. "
                 "eBay US$* = menor anúncio ativo plausível no eBay US (Browse "
                 "API; Buy It Now, item nos EUA, número no título, sem "
                 "graded/não-EN pelo título) — match por BUSCA, condição NÃO "
                 "garantida NM → informativo, nunca decide o veredito; exige "
                 "EBAY_CLIENT_ID/SECRET. COMC US$* = menor listagem banda "
                 "EX-NM ungraded EN na COMC (via Firecrawl, opt-in "
                 "--comc-price, créditos pagos) — banda EX-NM inclui EX → "
                 "informativo, nunca decide o veredito. Anúncio abaixo de 50% "
                 "da ref é lixo provável: pulado e contado em toda fonte. O "
                 "veredito compara o anúncio NM-EN coletado (CardTrader, único "
                 "com filtro NM+EN estruturado) com a referência market do "
                 "TCGPlayer (média de vendas, não é anúncio); CT abaixo de 50% "
                 "da ref sai como ⚠️ suspeito (provável variante errada), "
                 "nunca como vencedor. Liga/MYP: sem preço automatizado (MYP: "
                 "API atrás de Cloudflare — ver availability.py) — links de "
                 "busca pra conferência manual. Decisão é do operador._")
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
