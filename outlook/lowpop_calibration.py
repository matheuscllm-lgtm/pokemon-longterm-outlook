"""Calibração das faixas do modo low pop — com DADO, não de cabeça.

As faixas de Escassez (`SCARCITY_POP10_BANDS`) e Demanda (`DEMAND_SALES_BANDS`)
em `scoring.py` nasceram provisórias (sonda de 30 cartas só provou a FONTE).
Este módulo lê o que um run `--lowpop` deixou em disco e responde, com números:

  1. como o censo de PSA 10 e as vendas/mês se DISTRIBUEM no pool medido
     (quantis) — e por era;
  2. que fatia do pool cai em cada faixa VIGENTE (faixa vazia = componente que
     não discrimina; faixa com 60% do pool = idem);
  3. uma PROPOSTA de cortes por quantis, arredondados pra números "redondos"
     em escala log (1 · 1,5 · 2 · 3 · 5 · 7 × 10^k), com a fatia resultante;
  4. o prêmio PSA 10 ÷ crua (insumo da decisão "prêmio entra no score?") e a
     correlação escassez × demanda (as duas medidas são independentes?).

Fontes (ambas gitignored, escritas pelo run):
  - `data/snapshots/snapshot_<dia>.csv` (history.py): o POOL que entrou no
    ranking (só slabs dentro do teto), com era/raridade/pontos;
  - `data/cache/pricecharting/*.json` (psa10.py): TODA consulta bem-sucedida,
    inclusive as acima do teto — contexto do universo consultado.

Não muda nada sozinho: quem decide o corte é quem lê o relatório; a faixa nova
vai pra `scoring.py` por PR, com este relatório colado no CLAUDE.md.

CLI: `python -m outlook.lowpop_calibration [--snapshot CAMINHO] [--bands N]`
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from statistics import median
from typing import Iterable, Sequence

from . import history
from .psa10 import CACHE_DIR
from .scoring import (DEMAND_FLOOR, DEMAND_SALES_BANDS, SCARCITY_FLOOR,
                      SCARCITY_POP10_BANDS, demand_points, pop_trust_issue,
                      scarcity_points)
from .validate import spearman

NICE_MANTISSAS = (1.0, 1.5, 2.0, 3.0, 5.0, 7.0)
QUANTILES = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)


# ── Leitura ──────────────────────────────────────────────────────────────────

def load_pool(snapshot: Path | None = None) -> list[dict]:
    """Linhas do snapshot com `lowpop=1` (o pool que entrou no ranking).

    Sem caminho, usa o snapshot mais recente. Campos numéricos já convertidos;
    vazio vira None (nunca zero — ausência não é medida).
    """
    if snapshot is None:
        snaps = history.list_snapshots()
        if not snaps:
            return []
        snapshot = snaps[-1]
    rows = []
    with Path(snapshot).open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("lowpop") != "1":
                continue
            rows.append({
                "name": r["name"], "number": r["number"],
                "set_name": r["set_name"], "series": r["series"],
                "rarity": r["rarity"], "notorious": r.get("notorious") or "",
                "market_usd": _num(r.get("market_usd")),
                "psa10_usd": _num(r.get("psa10_usd")),
                "spm": _num(r.get("psa10_sales_per_month")),
                "pop10": _int(r.get("pop_psa10")),
                "pop_total": _int(r.get("pop_total")),
                "pts_character": _int(r.get("pts_character")) or 0,
                "pts_rarity": _int(r.get("pts_rarity")) or 0,
                "pts_scarcity": _int(r.get("pts_scarcity")),
                "pts_demand": _int(r.get("pts_demand")),
            })
    return rows


def load_cache(cache_dir: Path | None = None) -> list[dict]:
    """Toda consulta `status == ok` guardada pelo psa10.py (inclui acima do teto)."""
    d = cache_dir or CACHE_DIR
    out = []
    if not d.exists():
        return out
    for p in sorted(d.glob("*.json")):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if j.get("status") != "ok":
            continue
        pop = j.get("pop_psa")
        out.append({
            "psa10_usd": j.get("usd"), "spm": j.get("sales_per_month"),
            "raw_usd": j.get("raw_usd"),
            "pop10": pop[9] if pop else None,
            "pop_total": sum(pop) if pop else None,
        })
    return out


def _num(s) -> float | None:
    try:
        return float(s) if s not in (None, "") else None
    except ValueError:
        return None


def _int(s) -> int | None:
    v = _num(s)
    return int(v) if v is not None else None


# ── Estatística (stdlib, determinística) ─────────────────────────────────────

def quantile(xs: Sequence[float], q: float) -> float:
    """Quantil por interpolação linear (mesma convenção do numpy default)."""
    if not xs:
        raise ValueError("quantile de lista vazia")
    s = sorted(xs)
    if len(s) == 1:
        return float(s[0])
    pos = (len(s) - 1) * q
    lo = math.floor(pos)
    hi = min(lo + 1, len(s) - 1)
    return float(s[lo] + (s[hi] - s[lo]) * (pos - lo))


def nice_log(x: float) -> float:
    """Arredonda pro número 'redondo' mais próximo em escala log (1·1,5·2·3·5·7 × 10^k).

    Corte de faixa tem que ser memorizável ("≤ 300 slabs", "≥ 5 vendas/mês"),
    não 287,4 — e a diferença que importa é ordem de grandeza.
    """
    if x <= 0:
        return 0.0
    exp = math.floor(math.log10(x))
    best, best_d = None, None
    for e in (exp - 1, exp, exp + 1):
        for m in NICE_MANTISSAS:
            cand = m * 10 ** e
            d = abs(math.log10(cand) - math.log10(x))
            if best_d is None or d < best_d:
                best, best_d = cand, d
    return float(best)


def band_shares_le(values: Sequence[float], bands, floor_pts: int) -> list[tuple[str, int, int]]:
    """Fatia por faixa 'valor ≤ cap' (escassez): [(rótulo, pts, n)]."""
    out, prev = [], None
    remaining = list(values)
    for cap, pts in bands:
        n = sum(1 for v in remaining if v <= cap)
        remaining = [v for v in remaining if v > cap]
        lbl = f"≤{_fmt(cap)}" if prev is None else f"{_fmt(prev)}<x≤{_fmt(cap)}"
        out.append((lbl, pts, n))
        prev = cap
    out.append((f">{_fmt(prev)}", floor_pts, len(remaining)))
    return out


def band_shares_ge(values: Sequence[float], bands, floor_pts: int) -> list[tuple[str, int, int]]:
    """Fatia por faixa 'valor ≥ piso' (demanda): [(rótulo, pts, n)]."""
    out, prev = [], None
    remaining = list(values)
    for floor, pts in bands:
        n = sum(1 for v in remaining if v >= floor)
        remaining = [v for v in remaining if v < floor]
        lbl = f"≥{_fmt(floor)}" if prev is None else f"{_fmt(floor)}≤x<{_fmt(prev)}"
        out.append((lbl, pts, n))
        prev = floor
    out.append((f"<{_fmt(prev)}", floor_pts, len(remaining)))
    return out


def propose_bands_le(values: Sequence[float], pts_ladder: Sequence[int],
                     qs: Sequence[float] | None = None) -> tuple:
    """Cortes de escassez nos quantis (arredondados), mantendo a escada de pontos.

    Default: quantis igualmente espaçados — N faixas ≈ N fatias iguais do pool.
    O último degrau da escada é o piso (fica fora dos cortes).
    """
    n_cuts = len(pts_ladder) - 1
    qs = qs or [(i + 1) / (n_cuts + 1) for i in range(n_cuts)]
    cuts, last = [], None
    for q, pts in zip(qs, pts_ladder):
        c = nice_log(quantile(values, q))
        if last is not None and c <= last:  # cortes têm que crescer
            c = nice_log(last * 1.5)
        cuts.append((c, pts))
        last = c
    return tuple(cuts)


def propose_bands_ge(values: Sequence[float], pts_ladder: Sequence[int],
                     qs: Sequence[float] | None = None) -> tuple:
    """Cortes de demanda nos quantis (do alto pro baixo), mantendo a escada."""
    n_cuts = len(pts_ladder) - 1
    qs = qs or [1 - (i + 1) / (n_cuts + 1) for i in range(n_cuts)]
    cuts, last = [], None
    for q, pts in zip(qs, pts_ladder):
        c = nice_log(quantile(values, q))
        if last is not None and c >= last:  # cortes têm que decrescer
            c = nice_log(last / 1.5)
        cuts.append((c, pts))
        last = c
    return tuple(cuts)


def _fmt(x: float) -> str:
    return f"{x:g}"


# ── Relatório ────────────────────────────────────────────────────────────────

def _q_row(label: str, xs: Sequence[float]) -> str:
    cells = " | ".join(_fmt(round(quantile(xs, q), 1)) for q in QUANTILES)
    return f"| {label} | {len(xs)} | {cells} |"


def _shares_table(title: str, rows: list[tuple[str, int, int]], total: int) -> list[str]:
    out = [f"**{title}**", "", "| Faixa | Pts | n | % do pool |", "|---|---|---|---|"]
    for lbl, pts, n in rows:
        pct = (100.0 * n / total) if total else 0.0
        out.append(f"| {lbl} | {pts} | {n} | {pct:.0f}% |")
    out.append("")
    return out


def rescore(pool: Iterable[dict], sc_bands, sc_floor, dm_bands, dm_floor) -> list[tuple[int, dict]]:
    """Score de cada carta do pool sob faixas alternativas (Personagem + Raridade fixos).

    Linha sem censo confiável mantém `pts_scarcity` do snapshot (já é a régua
    de idade); sem vendas mantém `pts_demand` (já é a faixa de preço).
    """
    out = []
    for r in pool:
        s = r["pts_scarcity"] if r["pts_scarcity"] is not None else 0
        if r.get("_trusted"):
            s = _pts_le(r["pop10"], sc_bands, sc_floor)
        d = r["pts_demand"] if r["pts_demand"] is not None else 0
        if r["spm"] is not None:
            d = _pts_ge(r["spm"], dm_bands, dm_floor)
        out.append((r["pts_character"] + r["pts_rarity"] + s + d, r))
    return sorted(out, key=lambda t: (-t[0], -(t[1]["market_usd"] or 0)))


def census_trusted(pop10: int | None, pop_total: int | None,
                   spm: float | None) -> bool:
    """Espelho de `scoring.pop_trust_issue` sobre as colunas do snapshot."""
    if pop10 is None or pop_total is None:
        return False
    issue = pop_trust_issue([0] * 9 + [pop10] if pop_total == pop10
                            else [pop_total - pop10] + [0] * 8 + [pop10], spm)
    return issue is None


def _pts_le(v, bands, floor):
    for cap, pts in bands:
        if v <= cap:
            return pts
    return floor


def _pts_ge(v, bands, floor):
    for fl, pts in bands:
        if v >= fl:
            return pts
    return floor


def build_report(pool: list[dict], cache: list[dict], n_top: int = 30,
                 proposed_sc=None, proposed_dm=None) -> str:
    """Markdown com distribuição, fatias por faixa (vigente × proposta) e efeito no topo."""
    L = ["# Calibração do modo low pop", ""]
    if not pool:
        L.append("_Sem pool low pop no snapshot — rode `run_outlook.py --lowpop` antes._")
        return "\n".join(L)

    # Confiança do censo = a MESMA regra do scoring (`pop_trust_issue`), refeita
    # a partir do que o snapshot guarda (pop10 + total). Não dá pra inferir
    # pela pontuação: Escassez por idade e por censo podem coincidir (25 = 25).
    for r in pool:
        r["_trusted"] = census_trusted(r["pop10"], r["pop_total"], r["spm"])
    trusted = [r for r in pool if r["_trusted"]]
    with_spm = [r for r in pool if r["spm"] is not None]
    pop10 = [float(r["pop10"]) for r in trusted]
    spm = [r["spm"] for r in with_spm]

    L += [f"Pool medido (dentro do teto): **{len(pool)}** cartas · censo confiável: "
          f"**{len(trusted)}** · com vendas/mês: **{len(with_spm)}** · "
          f"consultas em cache (inclui acima do teto): **{len(cache)}**", ""]

    # Distribuição
    hdr = "| Métrica | n | " + " | ".join(f"p{int(q*100)}" for q in QUANTILES) + " |"
    L += ["## Distribuição (quantis)", "", hdr, "|---|---|" + "---|" * len(QUANTILES)]
    if pop10:
        L.append(_q_row("Pop PSA 10 (pool, censo confiável)", pop10))
    if spm:
        L.append(_q_row("Vendas/mês PSA 10 (pool)", spm))
    cache_pop = [float(c["pop10"]) for c in cache if c["pop10"] is not None
                 and c["pop_total"] and c["pop_total"] >= 25]
    cache_spm = [c["spm"] for c in cache if c["spm"] is not None]
    if cache_pop:
        L.append(_q_row("Pop PSA 10 (todas as consultas)", cache_pop))
    if cache_spm:
        L.append(_q_row("Vendas/mês (todas as consultas)", cache_spm))
    prem = [c["psa10_usd"] / c["raw_usd"] for c in cache
            if c["psa10_usd"] and c["raw_usd"]]
    if prem:
        L.append(_q_row("Prêmio PSA 10 ÷ crua (todas as consultas)", prem))
    L.append("")

    # Por era
    L += ["## Por era (pool)", "", "| Era | n | pop10 mediana | vendas/mês mediana | PSA 10 US$ mediana |",
          "|---|---|---|---|---|"]
    by = {}
    for r in pool:
        by.setdefault(r["series"], []).append(r)
    for era, rs in sorted(by.items()):
        p = [r["pop10"] for r in rs if r["_trusted"]]
        s = [r["spm"] for r in rs if r["spm"] is not None]
        u = [r["psa10_usd"] for r in rs if r["psa10_usd"] is not None]
        L.append(f"| {era} | {len(rs)} | {_fmt(median(p)) if p else '—'} | "
                 f"{_fmt(round(median(s), 1)) if s else '—'} | "
                 f"{_fmt(round(median(u))) if u else '—'} |")
    L.append("")

    # Independência das duas medidas
    both = [(float(r["pop10"]), r["spm"]) for r in trusted if r["spm"] is not None]
    if len(both) >= 5:
        rho = spearman([b[0] for b in both], [b[1] for b in both])
        L += [f"Spearman pop10 × vendas/mês (n={len(both)}): **{rho:+.2f}** "
              "(perto de 0 = medem coisas diferentes; muito positivo = quem tem "
              "mais slabs vende mais, e o par escassez+demanda se anula).", ""]

    # Faixas vigentes
    L += ["## Faixas VIGENTES — fatia do pool", ""]
    if pop10:
        L += _shares_table("Escassez (pop PSA 10)",
                           band_shares_le(pop10, SCARCITY_POP10_BANDS, SCARCITY_FLOOR), len(pop10))
    if spm:
        L += _shares_table("Demanda (vendas/mês)",
                           band_shares_ge(spm, DEMAND_SALES_BANDS, DEMAND_FLOOR), len(spm))

    # Proposta
    sc_ladder = [p for _, p in SCARCITY_POP10_BANDS] + [SCARCITY_FLOOR]
    dm_ladder = [p for _, p in DEMAND_SALES_BANDS] + [DEMAND_FLOOR]
    if proposed_sc is None and pop10:
        proposed_sc = propose_bands_le(pop10, sc_ladder)
    if proposed_dm is None and spm:
        proposed_dm = propose_bands_ge(spm, dm_ladder)
    L += ["## Faixas PROPOSTAS (quantis arredondados em escala log)", ""]
    if proposed_sc:
        L += [f"`SCARCITY_POP10_BANDS = {tuple((int(c), p) for c, p in proposed_sc)}`", ""]
        L += _shares_table("Escassez (proposta)",
                           band_shares_le(pop10, proposed_sc, SCARCITY_FLOOR), len(pop10))
    if proposed_dm:
        L += [f"`DEMAND_SALES_BANDS = {tuple((float(c), p) for c, p in proposed_dm)}`", ""]
        L += _shares_table("Demanda (proposta)",
                           band_shares_ge(spm, proposed_dm, DEMAND_FLOOR), len(spm))

    # Efeito no topo — só quem DISPUTA o ranking (censo confiável), como no
    # report.py: linha com pop não confiável vai pro balde à parte, não pro topo.
    if proposed_sc and proposed_dm:
        cur = rescore(trusted, SCARCITY_POP10_BANDS, SCARCITY_FLOOR,
                      DEMAND_SALES_BANDS, DEMAND_FLOOR)[:n_top]
        new = rescore(trusted, proposed_sc, SCARCITY_FLOOR, proposed_dm, DEMAND_FLOOR)[:n_top]
        key = lambda r: (r["name"], r["set_name"], r["number"])
        cur_k = {key(r) for _, r in cur}
        new_k = {key(r) for _, r in new}
        overlap = len(cur_k & new_k)
        eras_cur = _era_mix(cur)
        eras_new = _era_mix(new)
        L += [f"## Efeito no top {n_top} (só cartas com censo confiável, como no ranking)", "",
              f"- Sobreposição vigente × proposta: **{overlap}/{n_top}**",
              f"- Mix de eras (vigente): {eras_cur}",
              f"- Mix de eras (proposta): {eras_new}",
              f"- Score máximo/mínimo do top: vigente {cur[0][0]}/{cur[-1][0]} · "
              f"proposta {new[0][0]}/{new[-1][0]}", ""]
        L += ["| # | Carta | Era | pop10 | vendas/mês | score vigente → proposta |",
              "|---|---|---|---|---|---|"]
        cur_score = {key(r): s for s, r in rescore(trusted, SCARCITY_POP10_BANDS, SCARCITY_FLOOR,
                                                    DEMAND_SALES_BANDS, DEMAND_FLOOR)}
        for i, (s, r) in enumerate(new, 1):
            L.append(f"| {i} | {r['name']} {r['number']} ({r['set_name']}) | {r['series']} | "
                     f"{r['pop10'] if r['pop10'] is not None else '—'} | "
                     f"{_fmt(r['spm']) if r['spm'] is not None else '—'} | "
                     f"{cur_score[key(r)]} → {s} |")
        L.append("")
    return "\n".join(L)


def _era_mix(ranked) -> str:
    cnt = {}
    for _, r in ranked:
        cnt[r["series"]] = cnt.get(r["series"], 0) + 1
    return ", ".join(f"{k} {v}" for k, v in sorted(cnt.items(), key=lambda kv: -kv[1]))


def parse_cuts(text: str, pts_ladder: Sequence[int]) -> tuple:
    """'50,500,2000' + escada de pontos → ((50, 25), (500, 22), (2000, 18)).

    Exige exatamente um corte por degrau (o piso fica de fora) — a escada de
    pontos não muda na calibração, só os cortes.
    """
    cuts = [float(x) for x in text.split(",") if x.strip()]
    if len(cuts) != len(pts_ladder):
        raise ValueError(f"esperava {len(pts_ladder)} cortes (um por degrau "
                         f"{list(pts_ladder)}), recebi {len(cuts)}")
    return tuple(zip(cuts, pts_ladder))


def _run_cli() -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--snapshot", type=Path, default=None,
                    help="CSV do snapshot (default: o mais recente em data/snapshots/)")
    ap.add_argument("--top", type=int, default=30, help="tamanho do topo comparado")
    ap.add_argument("-o", "--output", type=Path, default=None,
                    help="grava o markdown também neste caminho")
    ap.add_argument("--scarcity", default=None,
                    help="cortes candidatos de Escassez (pop10 ≤ cap), ex. '50,500,2000,5000,10000'; "
                         "default = proposta automática por quantis")
    ap.add_argument("--demand", default=None,
                    help="cortes candidatos de Demanda (vendas/mês ≥ piso), ex. '60,30,5,2'; "
                         "default = proposta automática por quantis")
    a = ap.parse_args()
    sc = parse_cuts(a.scarcity, [p for _, p in SCARCITY_POP10_BANDS]) if a.scarcity else None
    dm = parse_cuts(a.demand, [p for _, p in DEMAND_SALES_BANDS]) if a.demand else None
    md = build_report(load_pool(a.snapshot), load_cache(), n_top=a.top,
                      proposed_sc=sc, proposed_dm=dm)
    print(md)
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(md, encoding="utf-8")


if __name__ == "__main__":
    _run_cli()
