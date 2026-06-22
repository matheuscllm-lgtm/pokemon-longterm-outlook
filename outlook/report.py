"""Relatório de cenário + tabela ranqueada — entrega em markdown.

Duas partes:
  1. CENÁRIO: panorama por era (nº de sets, idade, quantos já estão fora de
     impressão, mediana de preço dos chases) — tudo derivado dos DADOS do
     run, nada de opinião enlatada.
  2. RANKING: top-N cartas por score de longo prazo. O nome da carta vem com
     o número junto ("Mew V ... #251") e cada linha traz o link do gráfico no
     PriceCharting. O detalhamento dos 4 componentes saiu da tabela (a pedido
     do operador); o total continua, com o racional no rodapé.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median
from urllib.parse import quote_plus

from .scoring import ScoredCard


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|")


def _pricecharting_search_url(name: str, set_name: str, number: str) -> str:
    """Link da carta no PriceCharting (a página do produto traz o gráfico).

    Usa a BUSCA do PriceCharting em vez de montar uma URL /game/<slug> direta:
    o slug do set no PC não bate com o nome do tcgcsv e arriscaria 404. A busca
    sempre resolve (e cai na página da carta, onde está o gráfico histórico).
    O prefixo de era ("SV03: ", "SWSH07: ") é removido pra não poluir a query.
    """
    set_part = set_name
    if ":" in set_name:
        prefix, rest = set_name.split(":", 1)
        if len(prefix) <= 8:          # SV03 / SWSH07 / ME01...
            set_part = rest.strip()
    q = quote_plus(f"pokemon {set_part} {name} {number}".strip())
    return f"https://www.pricecharting.com/search-products?type=prices&q={q}"


def scenario_markdown(cards: list[ScoredCard], sets_meta: list[dict],
                      skipped_no_price: int, source: str = "tcgcsv") -> str:
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
    src_label = ("tcgcsv.com (dump diário do TCGPlayer)" if source == "tcgcsv"
                 else "pokemontcg.io (ao vivo)")
    lines.append(f"Cartas sem preço TCGPlayer na fonte (fora da análise): "
                 f"{skipped_no_price}. Fonte: {src_label} — preços market "
                 f"TCGPlayer.")
    return "\n".join(lines)


def _trend_footnote(trend_source: str) -> str:
    """Frase de honestidade sobre a coluna Tendência, conforme a fonte usada."""
    if trend_source == "tcgcsv":
        return (" Tendência = variação do marketPrice TCGPlayer entre hoje e o "
                "ponto histórico mais distante disponível (até 1 ano), série "
                "diária REAL do tcgcsv.com desde 2024-02-08, casada por "
                "productId; é histórico de fato, não previsão.")
    if trend_source == "pricecharting":
        return (" Tendência vem de ~6 vendas públicas do PriceCharting "
                "(amostra minúscula, indício apenas).")
    return ""


def ranking_markdown(cards: list[ScoredCard], top_n: int,
                     trend_source: str = "") -> str:
    ranked = sorted(cards, key=lambda c: (-c.score, -c.market_usd))[:top_n]
    lines = [f"## Top {len(ranked)} — score de longo prazo "
             f"(heurística 0-100; decisão é do operador)", ""]
    lines.append("| # | Score | Carta | Set | Raridade | ⭐ | Preço US$ | "
                 "Idade | Tendência | Notas | TCG | Gráfico (PriceCharting) |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, c in enumerate(ranked, 1):
        star = f"⭐ {c.notorious}" if c.notorious else ""
        notes = "; ".join(c.notes) if c.notes else ""
        carta = _md_escape(c.name)
        if c.number:
            carta += f" #{_md_escape(c.number)}"
        pc_url = _pricecharting_search_url(c.name, c.set_name, c.number)
        lines.append(
            f"| {i} | **{c.score}** | {carta} | "
            f"{_md_escape(c.set_name)} | {_md_escape(c.rarity)} | "
            f"{star} | {c.market_usd:.2f} | {c.age_months}m | "
            f"{c.trend or '—'} | {_md_escape(notes)} | "
            f"[TCG]({c.tcg_url}) | [📈 gráfico]({pc_url}) |")
    lines.append("")
    lines.append("_Score = Personagem + Raridade + Supply + Preço (0-25 cada, "
                 "somados) — o detalhamento por componente saiu da tabela a "
                 "pedido; segue heurística de triagem com racional aberto, NÃO "
                 "é previsão nem conselho (a Tendência é informativa e NÃO entra "
                 "no score). Gráfico = página da carta no PriceCharting (busca), "
                 "onde fica o histórico visual." + _trend_footnote(trend_source)
                 + "_")
    return "\n".join(lines)
