"""Relatório de cenário + tabela ranqueada — entrega em markdown.

Duas partes:
  1. CENÁRIO: panorama por era (nº de sets, idade, quantos já estão fora de
     impressão, mediana de preço dos chases) — tudo derivado dos DADOS do
     run, nada de opinião enlatada.
  2. RANKING: top-N cartas por score de longo prazo. O nome da carta vem com
     o número junto ("Mew V ... #251") e cada linha traz eBay, TCGPlayer e
     PriceCharting na coluna Links. O detalhamento dos 4 componentes saiu da
     tabela (a pedido do operador); o total continua, com o racional no rodapé.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median
from urllib.parse import quote_plus

from .availability import ebay_url
from .pricecharting import SEARCH as _PRICECHARTING_SEARCH
from .scoring import ScoredCard
from .sets import strip_era_prefix


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|")


def _md_link(label: str, url: str) -> str:
    """Link markdown seguro pra dentro de uma célula de tabela.

    Codifica os chars que quebrariam a tabela/link se aparecessem na URL:
    '|' (delimita célula) e '(' / ')' (a sem-par fecha o link cedo). URLs reais
    de TCGPlayer/PriceCharting não têm esses chars (conferido em 476 cartas),
    mas isto blinda a renderização contra fontes de URL futuras.
    """
    safe = url.replace("|", "%7C").replace("(", "%28").replace(")", "%29")
    return f"[{label}]({safe})"


def _pricecharting_search_url(name: str, set_name: str, number: str) -> str:
    """Link de BUSCA do PriceCharting pra carta (cai na página/gráfico dela).

    Busca em vez de URL /game/<slug> direta: o slug do set no PC não bate com o
    nome do tcgcsv e arriscaria 404; a busca sempre resolve. Reaproveita a base
    `SEARCH` do módulo pricecharting (fonte única da URL) e o `strip_era_prefix`
    compartilhado (tira "SV03: "/"SWSH07: " pra não poluir a query);
    `" ".join(...split())` colapsa espaços caso algum trecho venha vazio.
    """
    terms = " ".join(
        f"pokemon {strip_era_prefix(set_name)} {name} {number}".split())
    return _PRICECHARTING_SEARCH.format(q=quote_plus(terms))


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


def _fmt_pop(c: ScoredCard) -> str:
    """'PSA10 / total' + fonte, ou n/d."""
    if c.pop_psa10 is None or c.pop_total is None:
        return "n/d"
    src = {"gemrate": " PSA", "pricecharting": " PC"}.get(c.pop_source or "", "")
    return f"{c.pop_psa10:,} / {c.pop_total:,}" + src


def _fmt_gem_premium(c: ScoredCard) -> str:
    """'gem% · prêmio×' lado a lado (pedido do operador, 2026-10-17): os dois
    juntos dizem quanto a PSA 10 sai fácil e quanto ela vale sobre a crua."""
    gem = f"{c.gem_rate * 100:.0f}%" if c.gem_rate is not None else "n/d"
    prem = f"{c.psa10_premium:.1f}×" if c.psa10_premium is not None else "n/d"
    return f"{gem} · {prem}"


def _fmt_card(c: ScoredCard) -> str:
    """'Nome #286/217 · Set' numa célula só (pedido do operador, 2026-10-17)."""
    out = _md_escape(c.name)
    num = c.number_full or c.number
    if num:
        out += f" #{_md_escape(num)}"
    return f"{out} · {_md_escape(c.set_name)}"


def ranking_markdown(cards: list[ScoredCard], top_n: int,
                     trend_source: str = "", show_dh: bool = False,
                     graded: bool = False, lowpop: bool = False) -> str:
    graded = graded or lowpop  # low pop já inclui a leitura do slab
    # Modo low pop: carta cujo censo não vale (página fina/duplicada, pop n/d)
    # NÃO disputa o ranking com as medidas — cai no balde "validar manualmente"
    # no fim (padrão da frota), com o motivo na linha. Sem isso uma Gardevoir
    # ex 233 com "pop 1/2" empatava no topo (smoke 2026-09-21).
    unmeasured = [c for c in cards if lowpop and c.pop_issue]
    measured = [c for c in cards if not (lowpop and c.pop_issue)]
    ranked = sorted(measured, key=lambda c: (-c.score, -c.market_usd))[:top_n]
    lines = [f"## Top {len(ranked)} — score de longo prazo "
             f"(heurística 0-100; decisão é do operador)", ""]
    # Coluna DH (2ª opinião Double Holo) só entra quando houve --doubleholo.
    dh_h = "DH | " if show_dh else ""
    dh_sep = "---|" if show_dh else ""
    # Modo graded: o Preço do score é o do slab, então a tabela mostra PSA 10
    # e a liquidez dele (o preço raw vira contexto, não a régua).
    if lowpop:
        price_h = "PSA 10 US$ | Vendas/mês | Pop PSA10 / total | Gem · Prêmio | Raw US$ | "
        price_sep = "---|---|---|---|---|"
    elif graded:
        price_h = "PSA 10 US$ | Vendas/mês | Raw US$ | "
        price_sep = "---|---|---|"
    else:
        price_h = "Preço US$ | "
        price_sep = "---|"
    lines.append("| # | Score | " + dh_h + "Carta · nº · set | Raridade | ⭐ | "
                 + price_h + "Idade | Tendência | Notas | Links |")
    lines.append("|---|---|" + dh_sep + "---|---|---|" + price_sep
                 + "---|---|---|---|")
    def _row(i: int, c: ScoredCard) -> str:
        star = f"⭐ {c.notorious}" if c.notorious else ""
        notes = "; ".join(c.notes) if c.notes else ""
        pc_url = _pricecharting_search_url(c.name, c.set_name, c.number)
        links = " · ".join((
            _md_link('eBay (busca)', ebay_url(c.name, c.set_name, c.number)),
            _md_link('TCG', c.tcg_url) if c.tcg_url else '—',
            _md_link('📈 PriceCharting', pc_url),
        ))
        dh_c = (f"{c.dh_score if c.dh_score is not None else '—'} | "
                if show_dh else "")
        if graded:
            p10 = (f"{c.psa10_usd:.2f}" if c.psa10_usd is not None
                   else f"n/d ({c.psa10_status or 'sem consulta'})")
            spm = (f"{c.psa10_sales_per_month:g}"
                   if c.psa10_sales_per_month is not None else "n/d")
            if lowpop:
                price_c = (f"{p10} | {spm} | {_fmt_pop(c)} | "
                           f"{_fmt_gem_premium(c)} | {c.market_usd:.2f} | ")
            else:
                price_c = f"{p10} | {spm} | {c.market_usd:.2f} | "
        else:
            price_c = f"{c.market_usd:.2f} | "
        return (
            f"| {i} | **{c.score}** | " + dh_c + f"{_fmt_card(c)} | "
            f"{_md_escape(c.rarity)} | "
            f"{star} | " + price_c + f"{c.age_months}m | "
            f"{c.trend or '—'} | {_md_escape(notes)} | "
            f"{links} |")

    header = lines[-2:]  # cabeçalho + separador da tabela, reusado no balde
    for i, c in enumerate(ranked, 1):
        lines.append(_row(i, c))
    lines.append("")
    if unmeasured:
        lines.append("### ⚠️ Sem censo confiável — validar manualmente")
        lines.append("")
        lines.append("_Escassez NÃO medida (set com menos de 3 meses — censo "
                     "da PSA ainda em formação; set novo cujo censo mensal do "
                     "PriceCharting ainda não saiu; censo ausente; página "
                     "fina/duplicada no PriceCharting; ou mais vendas/mês do "
                     "que PSA 10 no censo): o score caiu na régua de idade do set e não "
                     "disputa o ranking acima. Motivo na coluna Notas._")
        lines.append("")
        lines.extend(header)
        for i, c in enumerate(
                sorted(unmeasured, key=lambda c: (-c.score, -c.market_usd)), 1):
            lines.append(_row(i, c))
        lines.append("")
    dh_note = (" DH = 2ª opinião do Double Holo (0-100, 50=neutro: previsão de "
               "preço + sinal IA + ROI de gradação + momentum); é avaliação dos "
               "dados do Double Holo, NÃO entra no score e NÃO é conselho de "
               "compra; '—' = sem dado Double Holo pra essa carta." if show_dh else "")
    graded_note = (" MODO GRADED: o componente Preço foi medido no slab "
                   "**PSA 10** (preço justo do PriceCharting, de vendas reais), "
                   "não no preço de carta crua — a coluna Raw US$ fica só como "
                   "contexto. Vendas/mês = liquidez do PSA 10; abaixo de 3/mês o "
                   "componente é tetado (preço de tabela num mercado ilíquido não "
                   "é preço realizável) e a linha ganha nota. Carta com PSA 10 "
                   "'n/d' manteve o Preço da régua raw, com o motivo declarado — "
                   "nunca inventamos preço nem liquidez." if graded else "")
    lowpop_note = (" MODO LOW POP: o score troca Supply e Preço por dois "
                   "componentes MEDIDOS na página do PriceCharting — "
                   "**Escassez** = nº de PSA 10 no censo e **Demanda** = "
                   "vendas/mês da PSA 10. Pop = 'PSA 10 / total gradado PSA' "
                   "+ fonte: **PSA** = pop oficial da PSA via "
                   "GemRate (diário); **PC** = censo do PriceCharting (foto "
                   "mensal, pode estar meses defasado em set novo — só entra "
                   "quando a carta não casou na GemRate). Gem · Prêmio = taxa "
                   "gem (PSA 10 ÷ total gradado) · PSA 10 ÷ carta crua "
                   "(informativos, não entram no score). "
                   "Censo ausente ou não confiável (set com <3 meses = censo da "
                   "PSA ainda em formação; set com <9 meses sem censo do "
                   "PriceCharting publicado; página fina/duplicada; ou mais "
                   "vendas/mês do que PSA 10 existentes) → Escassez cai "
                   "pra idade do set, com o motivo na linha; sem vendas "
                   "publicadas → Demanda cai pra faixa de preço, com nota. "
                   "Faixas calibradas em 2026-09-21 sobre o pool medido "
                   "(`python -m outlook.lowpop_calibration` recalibra)."
                   if lowpop else "")
    formula = ("Personagem + Raridade + Escassez + Demanda" if lowpop
               else "Personagem + Raridade + Supply + Preço")
    lines.append(f"_Score = {formula} (0-25 cada, "
                 "somados) — o detalhamento por componente saiu da tabela a "
                 "pedido; segue heurística de triagem com racional aberto, NÃO "
                 "é previsão nem conselho (a Tendência é informativa e NÃO entra "
                 "no score). eBay = busca da carta por nome, número e coleção, "
                 "sem filtro de graduação; não é anúncio verificado nem cotação. "
                 "PriceCharting = página da carta no PriceCharting (busca), "
                 "onde fica o histórico visual." + lowpop_note
                 + ("" if lowpop else graded_note) + dh_note
                 + _trend_footnote(trend_source) + "_")
    return "\n".join(lines)
