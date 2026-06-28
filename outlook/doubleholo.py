"""Coluna "DH" — avaliação dos dados do Double Holo (2ª opinião de mercado).

O que é: uma nota 0-100 que resume a LEITURA DE MERCADO do Double Holo para a
carta (previsão de preço, sinal de IA, ROI de gradação, momentum). É a avaliação
dos DADOS obtidos do Double Holo — uma **segunda opinião**, mostrada em uma
coluna à parte. **NÃO entra no score de longo prazo** (que continua 4×25=100).

50 = neutro. >50 = Double Holo otimista; <50 = pessimista.

Fonte dos dados: o JSON canônico produzido por
`~/scanners-commons/tooling/doubleholo_signals.py ingest --json` (que por sua vez
normaliza o que o DOM-scraper raspa da sua sessão premium logada). **A nota
`dh_score` é calculada UMA ÚNICA VEZ no pipeline (single source) e vem pronta no
JSON** — este módulo só a LÊ (não recalcula, pra não haver duas fórmulas que
divergem). O join com as cartas do outlook é por **productId do TCGPlayer**
(`tcg_product_id` no registro canônico == `ScoredCard.card_id`), determinístico —
sem casar por nome.
"""
from __future__ import annotations

import json


def load_signals(path: str) -> dict[str, dict]:
    """Lê o JSON canônico do pipeline -> {tcg_product_id: registro}.

    Aceita um registro único ou uma lista. Ignora registros sem product id
    (sem chave de join não dá pra casar com a carta — honesto, não inventa).
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    out: dict[str, dict] = {}
    for rec in data:
        pid = rec.get("tcg_product_id")
        if pid:
            out[str(pid)] = rec
    return out


def attach_scores(scored_cards, signals_by_pid: dict[str, dict]) -> int:
    """Seta `sc.dh_score` nas cartas cujo card_id (productId) casa. Devolve nº casados.

    Lê o `dh_score` precomputado no registro canônico (single source no pipeline
    `doubleholo_signals.py`). Registro casado sem o campo -> dh_score None ("—").
    """
    n = 0
    for sc in scored_cards:
        rec = signals_by_pid.get(str(sc.card_id))
        if rec is not None:
            sc.dh_score = rec.get("dh_score")
            n += 1
    return n
