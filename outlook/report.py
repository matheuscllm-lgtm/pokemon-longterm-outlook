"""Relatório de cenário + tabela ranqueada — entrega em markdown.

Duas partes:
  1. CENÁRIO: panorama por era (nº de sets, idade, quantos já estão fora de
     impressão, mediana de preço dos chases) — tudo derivado dos DADOS do
     run, nada de opinião enlatada.
  2. RANKING: top-N cartas por score de longo prazo, com os 4 componentes
     abertos por linha (transparência > caixa-preta).
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median

from .scoring import ScoredCard


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|")


def scenario_markdown(cards: list[ScoredCard], sets_meta: list[dict],
                      skipped_no_price: int) -> str:
    by_series: dict[str, list[ScoredCard]] = defaultdict(list)
    for c in cards:
        by_series[c.series].append(c)

    lines = ["## Cenário por era (derivado dos dados deste run)", ""]
    lines.append("| Era | Sets | Fora de impressão (>24m) | Cartas premium "
                 "analisadas | Mediana preço chase | Chase mais caro |")
    lines.append("|---|---|---|---|---|---|")
    sets_by_series: dict[str, list[dict]] = defaultdict(list)
    for s in sets_meta:
        sets_by_series[s.get("series", "?")].append(s)
    for series, cs in sorted(by_series.items()):
        smeta = sets_by_series.get(series, [])
        one_per_set = {c.set_id: c for c in cs}.values()
        oop = sum(1 for c in one_per_set
                  if c.age_months >= 24 and not c.heavy_reprint)
        prices = [c.market_usd for c in cs]
        top = max(cs, key=lambda c: c.market_usd)
        lines.append(
            f"| {series} | {len(smeta)} | {oop} | {len(cs)} | "
            f"${median(prices):.2f} | {_md_escape(top.name)} "
            f"({top.set_name} {top.number}) ${top.market_usd:.2f} |")
    lines.append("")
    lines.append(f"Cartas sem preço TCGPlayer na API (fora da análise): "
                 f"{skipped_no_price}. Fonte: pokemontcg.io (preços market "
                 f"TCGPlayer do dia).")
    return "\n".join(lines)


def ranking_markdown(cards: list[ScoredCard], top_n: int) -> str:
    ranked = sorted(cards, key=lambda c: (-c.score, -c.market_usd))[:top_n]
    lines = [f"## Top {len(ranked)} — score de longo prazo "
             f"(heurística 0-100; decisão é do operador)", ""]
    lines.append("| # | Score | Carta | Set | Nº | Raridade | ⭐ | Preço US$ | "
                 "Idade | Persngm | Rarid | Supply | Preço | Tendência | "
                 "Notas | Link TCG |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, c in enumerate(ranked, 1):
        star = f"⭐ {c.notorious}" if c.notorious else ""
        notes = "; ".join(c.notes) if c.notes else ""
        lines.append(
            f"| {i} | **{c.score}** | {_md_escape(c.name)} | "
            f"{_md_escape(c.set_name)} | {c.number} | {_md_escape(c.rarity)} | "
            f"{star} | {c.market_usd:.2f} | {c.age_months}m | "
            f"{c.pts_character} | {c.pts_rarity} | {c.pts_supply} | "
            f"{c.pts_price} | {c.trend or '—'} | {_md_escape(notes)} | "
            f"[TCG]({c.tcg_url}) |")
    lines.append("")
    lines.append("_Score = Personagem + Raridade + Supply + Preço (0-25 cada). "
                 "Heurística de triagem com racional aberto — NÃO é previsão "
                 "nem conselho de investimento; tendência (quando presente) "
                 "vem de ~6 vendas públicas do PriceCharting (amostra "
                 "minúscula, indício apenas)._")
    return "\n".join(lines)
