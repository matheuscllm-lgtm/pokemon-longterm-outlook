"""Validação do score — calibração (agora) + backtest longitudinal (com história).

O score nunca foi medido; os testes só checavam invariantes ("SIR > IR"). Este
módulo ataca a lacuna por dois caminhos:

A) CALIBRAÇÃO TRANSVERSAL (roda já, com o snapshot de hoje): num corte de
   mercado, cada componente deveria andar NO MESMO SENTIDO que o preço. Mede a
   correlação de postos (Spearman) componente × preço e compara medianas
   (carta notória vs não-notória dentro da mesma raridade). NÃO é prova de
   valorização futura — é checagem de sanidade dos pesos no mercado de HOJE.

B) BACKTEST LONGITUDINAL (precisa de história — outlook/history.py): para cards
   pontuados em t0, o preço subiu mais nos de score alto até o último snapshot?
   Sem ≥2 datas, avisa que falta coletar (a história nasce com os runs diários).

CLI: `python -m outlook.validate` baixa o universo padrão, calibra e, se houver
snapshots, roda o backtest.
"""
from __future__ import annotations

from datetime import date
from statistics import median
from typing import Sequence

from . import history


def _ranks(xs: list[float]) -> list[float]:
    """Postos médios (lida com empates) para Spearman."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(a: Sequence[float], b: Sequence[float]) -> float:
    n = len(a)
    if n < 2:
        return float("nan")
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va == 0 or vb == 0:
        return float("nan")
    return cov / (va ** 0.5 * vb ** 0.5)


def spearman(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b) or len(a) < 2:
        return float("nan")
    return _pearson(_ranks(list(a)), _ranks(list(b)))


def _flag(rho: float) -> str:
    if rho != rho:  # NaN
        return "—"
    if rho > 0.1:
        return "✅"
    if rho > -0.1:
        return "⚠️ fraco"
    return "❌ invertido"


def calibrate_cross_section(cards: list) -> str:
    if len(cards) < 10:
        return "Universo pequeno demais p/ calibrar (precisa ~10+ cartas)."
    price = [c.market_usd for c in cards]
    comps = {
        "Personagem": [c.pts_character for c in cards],
        "Raridade": [c.pts_rarity for c in cards],
        "Supply": [c.pts_supply for c in cards],
        "Preço (comp.)": [c.pts_price for c in cards],
        "SCORE total": [c.score for c in cards],
    }
    lines = ["## Calibração transversal (snapshot de hoje)", "",
             f"N = {len(cards)} cartas. Correlação de postos (Spearman) "
             "componente × preço de mercado (esperado: positivo):", "",
             "| Componente | ρ vs preço | |", "|---|---|---|"]
    for nm, xs in comps.items():
        rho = spearman(xs, price)
        lines.append(f"| {nm} | {rho:+.2f} | {_flag(rho)} |")
    sir = [c for c in cards if "special illustration" in (c.rarity or "").lower()]
    noto = [c.market_usd for c in sir if c.notorious]
    non = [c.market_usd for c in sir if not c.notorious]
    lines.append("")
    if noto and non:
        ok = median(noto) > median(non)
        lines.append(
            f"Dentro de SIR (n={len(sir)}): mediana NOTÓRIO ${median(noto):.2f} "
            f"(n={len(noto)}) vs NÃO-notório ${median(non):.2f} (n={len(non)}) — "
            + ("✅ prêmio de personagem confirmado" if ok
               else "⚠️ sem prêmio de personagem neste corte"))
    lines.append("")
    lines.append("_Calibração ≠ prova de valorização futura: é sanidade dos pesos "
                 "no mercado de HOJE. O componente Preço é não-monotônico de "
                 "propósito (pune >$300 e <$5), então ρ baixo/negativo nele é "
                 "esperado — não um erro._")
    return "\n".join(lines)


def backtest_longitudinal(min_days: int = 21) -> str:
    rows = history.load_rows()
    head = "## Backtest longitudinal\n\n"
    if not rows:
        return (head + "Sem snapshots ainda. Rode run_outlook.py por alguns "
                "dias/semanas — cada run salva 1 snapshot; com ≥2 datas "
                "espaçadas, o backtest passa a rodar aqui.")
    dates = sorted({r["date"] for r in rows})
    if len(dates) < 2:
        return (head + "Só 1 dia de história. Rode de novo em outra data para "
                "medir se score alto → maior valorização.")
    d0, d1 = dates[0], dates[-1]
    span = (date.fromisoformat(d1) - date.fromisoformat(d0)).days
    first = {r["card_id"]: r for r in rows if r["date"] == d0}
    last = {r["card_id"]: r for r in rows if r["date"] == d1}
    scores, rets = [], []
    for cid, r0 in first.items():
        r1 = last.get(cid)
        if not r1:
            continue
        p0, p1 = float(r0["market_usd"]), float(r1["market_usd"])
        if p0 <= 0:
            continue
        scores.append(int(r0["score"]))
        rets.append(100.0 * (p1 - p0) / p0)
    if len(scores) < 10:
        return head + f"Poucas cartas em comum entre {d0} e {d1} (n={len(scores)})."
    rho = spearman(scores, rets)
    paired = sorted(zip(scores, rets))
    q = max(1, len(paired) // 4)
    low = [r for _, r in paired[:q]]
    high = [r for _, r in paired[-q:]]
    lines = [head.rstrip("\n"), "",
             f"Janela: {d0} → {d1} ({span} dias), {len(scores)} cartas.", "",
             f"- Spearman(score em t0, retorno) = **{rho:+.2f}** "
             "(>0 = score alto rendeu mais — a hipótese da régua).",
             f"- Mediana de retorno do top-quartil de score: **{median(high):+.1f}%** "
             f"vs bottom-quartil: **{median(low):+.1f}%**."]
    if span < min_days:
        lines.append(f"\n⚠️ Janela curta ({span}d < {min_days}d): sinal ruidoso, "
                     "trate como preliminar.")
    return "\n".join(lines)


def _run_cli() -> None:
    from . import tcgcsv_api
    from .scoring import score_card
    eras = ["Scarlet & Violet", "Sword & Shield", "Mega Evolution"]
    print(f"Baixando universo p/ calibrar (eras {eras})...")
    sets_meta = tcgcsv_api.fetch_sets(eras)
    cards = []
    for s in sets_meta:
        for c in tcgcsv_api.fetch_cards_with_prices(s["id"]):
            usd = c.get("_market_usd")
            if usd and usd >= 5:
                cards.append(score_card(c, s, usd))
    print()
    print(calibrate_cross_section(cards))
    print()
    print(backtest_longitudinal())


if __name__ == "__main__":
    _run_cli()
