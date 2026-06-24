"""Helpers puros de nome de set (sem rede), compartilhados entre módulos.

Mora aqui pra não duplicar a mesma regra em report.py / availability.py — e,
por ser stdlib-only, qualquer um importa sem puxar `requests`.
"""
from __future__ import annotations


def strip_era_prefix(set_name: str) -> str:
    """'SWSH07: Evolving Skies' → 'Evolving Skies' (cru, sem normalizar caixa).

    Tira o prefixo de era numerado do tcgcsv ("SV03: ", "SWSH07: ", "ME01: ").
    Só corta quando o trecho antes do ':' é curto (≤ 8 chars) E sobra algo
    depois — assim não estraga um nome que use ':' de verdade (ex.:
    "Celebrations: Classic Collection") nem devolve string vazia (ex.: "SV03:"
    sem resto continua "SV03:"). Quem precisar de caixa/acento normalizados
    aplica isso por fora (ex.: availability._norm).
    """
    if ":" in set_name:
        prefix, rest = set_name.split(":", 1)
        rest = rest.strip()
        if rest and len(prefix) <= 8:
            return rest
    return set_name
