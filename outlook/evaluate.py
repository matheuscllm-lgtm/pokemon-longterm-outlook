"""Avaliador de calibração — fecha o loop do score contra preço realizado.

É a peça que faltava pra falar em "precisão": uma FUNÇÃO DE FITNESS. ASI-Evolve
(e, honestamente, qualquer melhoria de precisão) precisa de um número que diga
se o score ORDENA as cartas de forma consistente com o que o mercado fez. Este
módulo calcula esse número.

GROUND TRUTH (proxy, declaradamente fraco): a variação de preço das vendas
recentes do PriceCharting — a MESMA fonte/limitação da tendência do tool. É de
curto prazo e amostra minúscula (6 vendas/carta). Logo isto NÃO prova
valorização de longo prazo; mede se a ordenação do score bate com o movimento
realizado recente. É sinal de sanidade/triagem, não verdade. Por isso:
  - usamos correlação de POSTO (Spearman), porque o tool é um ranking, não um
    previsor de preço absoluto;
  - reportamos sempre o N efetivo (cartas com tendência válida);
  - abaixo de MIN_N a leitura é "amostra insuficiente" — não recalibrar.

A estatística é pura (sem numpy/scipy — o projeto só depende de requests) e
testada em tests/test_evaluate.py com dados sintéticos, sem rede.
"""
from __future__ import annotations

from dataclasses import dataclass

from .scoring import ScoredCard

MIN_N = 10      # abaixo disso, amostra insuficiente p/ qualquer leitura honesta
STRONG = 0.30   # |Spearman| abaixo disso = sinal fraco (não recalibrar)

# Componente -> como extraí-lo de uma carta pontuada (o total é c.score).
_COMPONENTS = {
    "Personagem": lambda c: c.pts_character,
    "Raridade": lambda c: c.pts_rarity,
    "Supply": lambda c: c.pts_supply,
    "Preço": lambda c: c.pts_price,
}


def _avg_ranks(values: list[float]) -> list[float]:
    """Postos médios 1-based; empates recebem a média dos postos que ocupam."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1  # média dos postos 1-based no bloco i..j
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Correlação de Pearson, ou None se N<2 ou variância zero."""
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    den = (sum(a * a for a in dx) * sum(b * b for b in dy)) ** 0.5
    if den == 0:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / den


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Correlação de posto: Pearson sobre os postos médios (trata empates)."""
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    return pearson(_avg_ranks(xs), _avg_ranks(ys))


@dataclass
class Calibration:
    n: int                                  # cartas com tendência válida
    n_total: int                            # cartas avaliadas (com e sem)
    fitness: float | None                   # Spearman(score, realizado)
    by_component: dict[str, float | None]   # Spearman de cada componente
    mean_trend: float | None                # variação realizada média (%)

    @property
    def sufficient(self) -> bool:
        return self.n >= MIN_N and self.fitness is not None

    @property
    def coverage(self) -> float:
        return self.n / self.n_total if self.n_total else 0.0


def calibrate(pairs: list[tuple[ScoredCard, float | None]]) -> Calibration:
    """Correlaciona score (e cada componente) com a variação realizada.

    `pairs`: (carta pontuada, variação % realizada ou None). Cartas sem
    tendência (None) entram só no n_total — nunca inventamos o ground truth.
    """
    valid = [(c, t) for c, t in pairs if t is not None]
    n, n_total = len(valid), len(pairs)
    none_by = {k: None for k in _COMPONENTS}
    if n < 2:
        return Calibration(n, n_total, None, none_by, None)
    trends = [t for _, t in valid]
    by = {name: spearman([f(c) for c, _ in valid], trends)
          for name, f in _COMPONENTS.items()}
    fitness = spearman([c.score for c, _ in valid], trends)
    return Calibration(n, n_total, fitness, by, sum(trends) / n)


def evaluator_payload(cal: Calibration) -> dict:
    """Contrato do ASI-Evolve: {'score': float, 'metrics': {...}}.

    O 'score' é o fitness que o loop evolutivo maximiza (Spearman do total).
    """
    return {
        "score": cal.fitness if cal.fitness is not None else 0.0,
        "metrics": {
            "n": cal.n,
            "n_total": cal.n_total,
            "coverage": round(cal.coverage, 3),
            "mean_trend_pct": (round(cal.mean_trend, 2)
                               if cal.mean_trend is not None else None),
            "sufficient": cal.sufficient,
            **{f"spearman_{k.lower()}": (round(v, 3) if v is not None else None)
               for k, v in cal.by_component.items()},
        },
    }


def _interp(r: float | None) -> str:
    """Lê uma correlação em palavras (sinal + força)."""
    if r is None:
        return "n/d"
    mag = abs(r)
    força = ("~nulo" if mag < 0.10 else "fraco" if mag < 0.30
             else "moderado" if mag < 0.50 else "forte")
    if força == "~nulo":
        return "~nulo"
    return f"{'+' if r > 0 else '−'} {força}"


def calibration_markdown(cal: Calibration, source: str = "tcgcsv") -> str:
    """Relatório de calibração em markdown (entrega no chat, regra do projeto)."""
    fit = "n/d" if cal.fitness is None else f"{cal.fitness:+.2f}"
    mean = "n/d" if cal.mean_trend is None else f"{cal.mean_trend:+.1f}%"
    lines = [
        "## Calibração: score × preço realizado (ASI-Evolve evaluator)",
        "",
        f"Cartas avaliadas: **{cal.n_total}** · com tendência válida (N): "
        f"**{cal.n}** ({cal.coverage*100:.0f}% de cobertura) · variação "
        f"realizada média: **{mean}**",
        "",
        f"**Fitness** (Spearman score × realizado): **{fit}**  "
        f"_(−1 a +1; quanto maior, melhor a ordenação)_",
        "",
        "| Componente | Spearman vs realizado | Leitura |",
        "|---|---|---|",
    ]
    for name, r in cal.by_component.items():
        val = "n/d" if r is None else f"{r:+.2f}"
        lines.append(f"| {name} | {val} | {_interp(r)} |")
    lines.append("")
    strongest = max((abs(r) for r in cal.by_component.values()
                     if r is not None), default=0.0)
    if not cal.sufficient:
        lines.append(
            f"**Veredito:** amostra insuficiente (N={cal.n} < {MIN_N}) — "
            "**não recalibrar**. Rode de novo com mais cartas.")
    elif strongest < STRONG:
        lines.append(
            f"**Veredito:** N={cal.n} ok, mas **sinal fraco** — nenhum "
            f"componente com |Spearman| ≥ {STRONG:.2f}. **Não recalibrar.** O "
            "ground truth é de CURTO prazo e não adjudica os pesos de um score "
            "de LONGO prazo. Correlação levemente negativa é compatível com "
            "reversão à média (blue-chips consolidando enquanto especulativas "
            "dão pico recente) — não é evidência contra a tese. Fitar isto "
            "viraria o tool num caçador de momentum.")
    else:
        lines.append(
            f"**Veredito:** N={cal.n} e há componente com |Spearman| ≥ "
            f"{STRONG:.2f} — candidato a ajuste de peso, **com cautela de "
            "horizonte** (curto prazo ≠ longo prazo). Mexa só no que tiver "
            "sinal claro e estável entre runs.")
    lines += [
        "",
        f"> ⚠️ **Honestidade obrigatória.** Ground truth = **{source}**: "
        "variação realizada de **curto prazo** (semana vs mês). Mede se a "
        "ORDENAÇÃO do score acompanha o movimento recente — **não** prova "
        "valorização de longo prazo, que é o que o score busca. Correlação de "
        "posto (Spearman) porque o tool é um ranking; ganhos pequenos = ruído.",
    ]
    return "\n".join(lines)
