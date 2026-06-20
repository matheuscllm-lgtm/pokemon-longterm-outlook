"""Política de score EVOLVÍVEL — ponto de partida do ASI-Evolve (cópia sandbox).

ASI-Evolve muta ESTE arquivo geração após geração, buscando maximizar o fitness
do evaluator.py (Spearman do score vs preço realizado). Quando um candidato
vence, porte os números de volta pra `outlook/scoring.py` (+ tiers em
`outlook/notorious.py`) — este arquivo é o laboratório, o tool é a entrega.

O que é EVOLVÍVEL aqui: só os PESOS/limiares chutados (as tabelas de pontos e
como os 4 componentes somam). O que NÃO está aqui (fica fixo no tool): a
curadoria de personagem→tier e a extração de features — isso é julgamento
humano, não palpite numérico. O evaluator passa as features prontas; aqui só
decidimos quantos pontos cada coisa vale.

Contrato: score_components(features) -> dict com os 4 componentes (0-25 cada).
features = {rarity:str, age_months:int, market_usd:float,
            appeal_tier:'S'|'A'|'B'|None, heavy_reprint:bool, alt_art:bool}
"""
from __future__ import annotations

# ── PESOS EVOLVÍVEIS (espelham outlook/scoring.py + notorious.py hoje) ────────
APPEAL_POINTS = {"S": 25, "A": 18, "B": 12, None: 8}

RARITY_RULES = [   # (substring na raridade, pontos) — primeiro match vence
    ("special illustration", 25), ("illustration", 20),
    ("trainer gallery", 16), ("character", 16),
    ("hyper", 14), ("secret", 14), ("rainbow", 14),
    ("amazing", 14), ("radiant", 14), ("shiny", 14),
    ("vmax", 12), ("vstar", 12), ("ultra", 12),
    ("ace spec", 10), ("double rare", 6), ("rare holo v", 6),
]
RARITY_DEFAULT = 3
ALT_ART_POINTS = 25       # nome marcado "(Alternate Art ...)" no TCGPlayer

SUPPLY_TIERS = [(36, 25), (24, 22), (18, 18), (12, 12), (6, 7)]  # (meses, pts)
SUPPLY_MIN = 3
REPRINT_CAP = 12          # set com reprint forte trava o supply aqui

PRICE_BUCKETS = [(5, 5), (15, 12), (40, 20), (120, 25), (300, 18)]  # (teto, pts)
PRICE_ABOVE = 12          # acima do último teto (já precificado)


def _rarity_points(rarity: str, alt_art: bool) -> int:
    if alt_art:
        return ALT_ART_POINTS
    r = (rarity or "").lower()
    for needle, pts in RARITY_RULES:
        if needle in r:
            return pts
    return RARITY_DEFAULT


def _supply_points(age_months: int, heavy_reprint: bool) -> int:
    pts = SUPPLY_MIN
    for months, p in SUPPLY_TIERS:
        if age_months >= months:
            pts = p
            break
    return min(pts, REPRINT_CAP) if heavy_reprint else pts


def _price_points(usd: float) -> int:
    for ceil, pts in PRICE_BUCKETS:
        if usd < ceil:
            return pts
    return PRICE_ABOVE


def score_components(features: dict) -> dict:
    return {
        "Personagem": APPEAL_POINTS.get(features.get("appeal_tier"), 8),
        "Raridade": _rarity_points(features["rarity"], features.get("alt_art", False)),
        "Supply": _supply_points(features["age_months"], features.get("heavy_reprint", False)),
        "Preço": _price_points(features["market_usd"]),
    }
