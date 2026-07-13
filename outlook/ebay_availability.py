"""eBay Browse API — menor anúncio ATIVO por carta (preço real, informativo).

O que é (e o que NÃO é):
  - Preço REAL de anúncio ativo no eBay US, via Browse API oficial (grátis,
    5.000 chamadas/dia) — mesmas chaves do ebay-arbitrage-scanner da frota:
    env vars `EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET` (sanitizadas contra
    BOM/zero-width; nunca logadas). Sem as chaves → n/d honesto (só link).
  - O match é por BUSCA (query de texto), não por identidade de produto —
    título arbitrário é a maior fonte de erro (lição da frota). Guards:
    o número de coleção TEM que aparecer no título; título com marcador de
    graded (PSA/BGS/CGC/SGC) ou de idioma não-EN é pulado; anúncio abaixo
    de SUSPECT_RATIO×ref é lixo provável (contado, nunca vencedor).
  - Mesmo com os guards, condição NM NÃO é garantida (o eBay não estrutura
    condição de carta crua) → a coluna é INFORMATIVA e o veredito NM-EN
    continua decidido só por fontes com filtro NM+EN real (CardTrader).

Nunca inventa preço: erro/sem chave/sem anúncio plausível → status explícito.
"""
from __future__ import annotations

import os
import re
import time
from typing import Optional

import requests

from .availability import SUSPECT_RATIO, _base_name, _clean_number, _clean_secret
from .sets import strip_era_prefix

EBAY_OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
EBAY_SCOPE = "https://api.ebay.com/oauth/api_scope"
EBAY_MARKETPLACE = "EBAY_US"
CCG_SINGLES_CATEGORY = "183454"   # CCG Individual Cards (mesma do scanner eBay)
TIMEOUT_S = 30
RETRIES = 3
REQUEST_DELAY_S = 0.35

# Título com esses marcadores sai do funil: graded não é comparável com raw,
# e carta não-EN não é comparável com a referência EN. Checagem por token no
# título minúsculo — conservador: na dúvida (sem marcador), o anúncio FICA,
# porque a coluna é informativa e o link permite conferir.
GRADED_MARKERS = ("psa", "bgs", "cgc", "sgc", "graded", "ace 10")
NON_EN_MARKERS = ("japanese", "japan", "jpn", "korean", "chinese", "german",
                  "italian", "french", "spanish", "portuguese")


def load_ebay_keys() -> Optional[tuple[str, str]]:
    """(client_id, client_secret) das env vars, ou None se faltarem."""
    cid = _clean_secret(os.environ.get("EBAY_CLIENT_ID"))
    secret = _clean_secret(os.environ.get("EBAY_CLIENT_SECRET"))
    if cid and secret:
        return cid, secret
    return None


def _title_matches(title: str, number: str) -> bool:
    """O número de coleção precisa aparecer no título (precisão > cobertura).

    Aceita "251", "251/264", "#251", "TG16" e zeros à esquerda ("072/078" casa
    o nº 72) — token delimitado: "214" NÃO casa dentro de "2149".
    """
    want = _clean_number(number).lower()
    if not want or want == "0":
        return False
    low = (title or "").lower()
    return re.search(rf"(?<![a-z0-9])0*{re.escape(want)}(?![0-9])", low) is not None


def _title_excluded(title: str) -> bool:
    low = (title or "").lower()
    return (any(m in low for m in GRADED_MARKERS)
            or any(m in low for m in NON_EN_MARKERS))


class EbayAvailability:
    """Menor anúncio ativo plausível no eBay US (Buy It Now, item nos EUA)."""

    def __init__(self, client_id: str, client_secret: str):
        self._auth = (client_id, client_secret)
        self._token: Optional[str] = None
        self._token_expiry = 0.0

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        r = requests.post(
            EBAY_OAUTH_URL, auth=self._auth,
            data={"grant_type": "client_credentials", "scope": EBAY_SCOPE},
            timeout=TIMEOUT_S)
        if r.status_code != 200:
            raise RuntimeError(f"eBay OAuth HTTP {r.status_code}")
        j = r.json()
        self._token = j["access_token"]
        self._token_expiry = time.time() + float(j.get("expires_in", 7200))
        return self._token

    def _search(self, query: str) -> list[dict]:
        last: Exception | None = None
        for attempt in range(RETRIES):
            time.sleep(REQUEST_DELAY_S * (attempt + 1))
            try:
                r = requests.get(
                    EBAY_SEARCH_URL,
                    headers={"Authorization": f"Bearer {self._get_token()}",
                             "X-EBAY-C-MARKETPLACE-ID": EBAY_MARKETPLACE},
                    params={"q": query,
                            "category_ids": CCG_SINGLES_CATEGORY,
                            "filter": ("buyingOptions:{FIXED_PRICE},"
                                       "itemLocationCountry:US"),
                            "sort": "price",
                            "limit": "50"},
                    timeout=TIMEOUT_S)
            except requests.RequestException as exc:
                last = RuntimeError(f"eBay rede: {exc}")
                continue
            if r.status_code == 200:
                return r.json().get("itemSummaries") or []
            last = RuntimeError(f"eBay HTTP {r.status_code}")
        raise last

    def cheapest(self, name: str, set_name: str, number: str,
                 ref_usd: Optional[float] = None) -> dict:
        """{'usd','url','status','junk_skipped'} — menor anúncio plausível.

        status: 'ok' | 'sem anúncio plausível' | 'erro: ...' — nunca silencioso.
        Preço = valor do item (frete NÃO incluído; o sort do eBay considera
        preço+frete, então a varredura dos 50 primeiros cobre o reordenamento).
        """
        query = " ".join(f"pokemon {_base_name(name)} {_clean_number(number)} "
                         f"{strip_era_prefix(set_name)}".split())
        try:
            items = self._search(query)
        except RuntimeError as exc:
            return {"status": f"erro: {exc}"}
        best, junk = None, 0
        for it in items:
            title = it.get("title") or ""
            if not _title_matches(title, number) or _title_excluded(title):
                continue
            price = (it.get("price") or {})
            if (price.get("currency") or "USD") != "USD":
                continue
            try:
                usd = float(price.get("value"))
            except (TypeError, ValueError):
                continue
            if ref_usd and ref_usd > 0 and usd < SUSPECT_RATIO * ref_usd:
                junk += 1
                continue
            if best is None or usd < best["usd"]:
                best = {"usd": usd, "url": it.get("itemWebUrl") or "",
                        "status": "ok"}
        if best:
            best["junk_skipped"] = junk
            return best
        if junk:
            return {"status": f"só anúncios-lixo ({junk} < 50% da ref)"}
        return {"status": "sem anúncio plausível"}
