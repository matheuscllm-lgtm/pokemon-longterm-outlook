"""Cliente do pokemontcg.io — catálogo, raridades, datas e preços TCGPlayer.

A API é gratuita; com a chave (env var POKEMONTCG_API_KEY) o limite diário
sobe pra 20.000 requests. Baixamos as cartas das séries-alvo inteiras com
paginação (pageSize 250) e filtramos localmente — é mais robusto do que
montar uma query por raridade (os NOMES de raridade variam entre eras).

Tudo aqui é leitura pública; nenhum preço é inventado: carta sem bloco
tcgplayer.prices sai do universo analisado (contada no relatório como
"sem preço").
"""
from __future__ import annotations

import os
import time
from typing import Iterator, Optional

import requests

API = "https://api.pokemontcg.io/v2"
PAGE_SIZE = 250
TIMEOUT_S = 30
RETRIES = 3


def _headers() -> dict[str, str]:
    h = {"User-Agent": "pokemon-longterm-outlook/0.1"}
    key = os.environ.get("POKEMONTCG_API_KEY", "").strip()
    if key:
        h["X-Api-Key"] = key
    return h


def _get(path: str, params: dict) -> dict:
    last_exc: Exception | None = None
    for attempt in range(RETRIES):
        try:
            r = requests.get(f"{API}/{path}", params=params,
                             headers=_headers(), timeout=TIMEOUT_S)
            if r.status_code == 200:
                return r.json()
            # 429/5xx: espera e tenta de novo; outros códigos = erro real.
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2.0 * (attempt + 1))
                last_exc = RuntimeError(f"HTTP {r.status_code} em /{path}")
                continue
            raise RuntimeError(f"HTTP {r.status_code} em /{path}: {r.text[:200]}")
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"pokemontcg.io indisponível após {RETRIES} tentativas: {last_exc}")


def fetch_sets(series_list: list[str]) -> list[dict]:
    """Todos os sets cujas séries estão em series_list (ex.: 'Scarlet & Violet')."""
    out: list[dict] = []
    page = 1
    while True:
        data = _get("sets", {"pageSize": PAGE_SIZE, "page": page})
        batch = data.get("data", [])
        out.extend(s for s in batch if s.get("series") in series_list)
        if len(batch) < PAGE_SIZE:
            return out
        page += 1


def fetch_cards_for_set(set_id: str, sleep_s: float = 0.0) -> Iterator[dict]:
    """Todas as cartas de um set (paginado)."""
    page = 1
    while True:
        data = _get("cards", {"q": f"set.id:{set_id}",
                              "pageSize": PAGE_SIZE, "page": page})
        batch = data.get("data", [])
        yield from batch
        if len(batch) < PAGE_SIZE:
            return
        page += 1
        if sleep_s:
            time.sleep(sleep_s)


def best_market_usd(card: dict) -> Optional[float]:
    """Preço 'market' TCGPlayer da variante principal da carta.

    Variantes reverse/1st-ed são ignoradas (a carta-chase é a versão normal/
    holo); entre as restantes pegamos o MAIOR market — pra cartas premium
    normalmente só existe uma variante mesmo.
    """
    prices = (card.get("tcgplayer") or {}).get("prices") or {}
    candidates = []
    for variant, block in prices.items():
        if "reverse" in variant.lower():
            continue
        m = (block or {}).get("market")
        if isinstance(m, (int, float)) and m > 0:
            candidates.append(float(m))
    return max(candidates) if candidates else None


def cardmarket_trend_pct(card: dict) -> Optional[float]:
    """Tendência realizada de curto prazo via CardMarket (avg7 vs avg30), em %.

    Ground truth ROBUSTO pra calibração: vem direto da pokemontcg.io (médias de
    venda dos últimos 7 e 30 dias), sem scraping. É a variação que o mercado de
    fato fez no último mês — curto prazo (mesma ressalva de sempre), mas real e
    disponível pra quase toda carta premium. None se faltar dado ou avg30<=0.

    Obs.: o nível de preço do CardMarket (EUR) difere do TCGPlayer (USD) usado
    no componente Preço, mas a VARIAÇÃO % é relativa — mede o mesmo movimento.
    """
    prices = (card.get("cardmarket") or {}).get("prices") or {}
    a7, a30 = prices.get("avg7"), prices.get("avg30")
    if not isinstance(a7, (int, float)) or not isinstance(a30, (int, float)):
        return None
    if a30 <= 0:
        return None
    return (a7 - a30) / a30 * 100


def tcgplayer_url(card: dict) -> str:
    url = (card.get("tcgplayer") or {}).get("url")
    if url:
        return url
    q = requests.utils.quote(card.get("name", ""))
    return ("https://www.tcgplayer.com/search/pokemon/product"
            f"?productLineName=pokemon&q={q}")
