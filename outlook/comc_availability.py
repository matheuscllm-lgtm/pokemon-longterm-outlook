"""COMC — menor listagem banda EX-NM ungraded por carta, via Firecrawl (OPT-IN).

O que é (e o que NÃO é):
  - Preço REAL de listagem na COMC, obtido renderizando a página de busca
    via Firecrawl (`FIRECRAWL_API_KEY` — a COMC é Cloudflare: acesso direto
    da nuvem = 403, provado no scanner-comc da frota). Cada carta = 1 fetch
    Firecrawl = CRÉDITOS PAGOS → a coleta é **opt-in** (`--comc-price` no
    run_availability); sem a flag ou sem a key, a COMC segue só como link.
  - A URL de busca já filtra no servidor: `fb` (Buy It Now), `aUngraded`
    (sem graded), `gEX-NM` (banda near-mint da COMC), `sl` (menor preço
    primeiro) — mesmo esquema do scanner-comc da frota.
  - O parse da página é o formato `carddata` real da COMC (reverse-engineered
    e testado no scanner-comc; fixture própria nos testes deste repo).
  - Filtros por listagem (allowlist, nunca substring — invariante da frota):
    condição na allowlist near-mint da COMC; número de coleção tem que casar;
    nome-base tem que casar; set que nomeia idioma não-EN é excluído (o preço
    de referência é do produto EM INGLÊS).
  - Mesmo assim o match é por BUSCA (não identidade) e a banda EX-NM inclui
    EX — a coluna é INFORMATIVA e o veredito NM-EN continua decidido só pelo
    CardTrader (filtro NM+EN estrito por propriedade estruturada).

Nunca inventa preço: sem key/flag/oferta plausível → status explícito.
"""
from __future__ import annotations

import html as _html
import os
import re
import time
import urllib.parse
from typing import Optional

import requests

from .availability import SUSPECT_RATIO, _base_name, _clean_number, _clean_secret, _norm

COMC_BASE = "https://www.comc.com"
FIRECRAWL_URL = "https://api.firecrawl.dev/v2/scrape"
TIMEOUT_S = 180
RETRIES = 2

# Allowlist de condição near-mint da COMC (igualdade, NUNCA substring — é
# assim que LP/SP não vazam; mesma lista fechada do scanner-comc da frota).
NM_CONDITION_ALLOW = ("nm", "mint", "m", "ex-nm", "exnm", "near mint")
# Set da COMC que nomeia outro idioma → fora (referência é o produto EN).
NON_EN_MARKERS = ("japanese", "japan", "korean", "chinese", "german",
                  "italian", "french", "spanish", "portuguese")

# Bloco de resultado real da COMC: <div class="carddata"> com o link de
# detalhe carregando set/número/nome/condição no path (formato provado no
# scanner-comc, 2026-06). Host opcional: rawHtml do Firecrawl vem absoluto.
_CARDDATA_SPLIT = re.compile(r'<div\s+class="carddata"\s*>', re.IGNORECASE)
_DETAIL_URL_RE = re.compile(
    r'href="((?:https?://(?:www\.)?comc\.com)?/Cards/Pokemon/'
    r'([^"/]+)/([^"]+?)/([^"/]+)/([^"/]+)/(\d+)/(Ungraded|Graded)/([^"/]+)/([^"/]+))"',
    re.IGNORECASE,
)
_QTY_RE = re.compile(r'<div\s+class="qty"\s*>\s*(\d+)\s+from', re.IGNORECASE)
_LISTPRICE_RE = re.compile(r'class="listprice', re.IGNORECASE)
_PRICE_RE = re.compile(r"\$\s?([0-9][0-9,]*\.?[0-9]{0,2})")


def load_firecrawl_key() -> Optional[str]:
    return _clean_secret(os.environ.get("FIRECRAWL_API_KEY"))


def comc_search_url(name: str) -> str:
    """Busca por nome, já filtrada no servidor (BIN + ungraded + banda EX-NM),
    ordenada do mais barato pro mais caro, 50 itens."""
    term = urllib.parse.quote_plus(name)
    return f"{COMC_BASE}/Cards/Pokemon,={term},sl,fb,aUngraded,gEX-NM,i50,p1"


def _deslug(segment: str) -> str:
    return _html.unescape(urllib.parse.unquote(segment or "")).replace("_", " ").strip()


def _to_float(text: str) -> Optional[float]:
    m = _PRICE_RE.search(text or "")
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_comc_page(html: str) -> list[dict]:
    """Página de busca COMC → [{'name','set','number','condition','graded',
    'price','qty','url'}] — um por bloco carddata."""
    out: list[dict] = []
    blocks = _CARDDATA_SPLIT.split(html)
    for block in blocks[1:]:
        m = _DETAIL_URL_RE.search(block)
        if not m:
            continue
        url, _year, set_seg, number_seg, name_seg, _id, graded_seg, _src, cond_seg = m.groups()
        if url.startswith("/"):
            url = COMC_BASE + url
        lp = _LISTPRICE_RE.search(block)
        price = _to_float(block[lp.end():] if lp else block)
        if price is None:
            continue
        qty_m = _QTY_RE.search(block)
        out.append({
            "name": _deslug(name_seg),
            "set": _deslug(set_seg),
            "number": _deslug(number_seg),
            "condition": _deslug(cond_seg),
            "graded": graded_seg.lower() == "graded",
            "price": price,
            "qty": int(qty_m.group(1)) if qty_m else 1,
            "url": url,
        })
    return out


def _is_challenge(html: str) -> bool:
    """Interstitial da Cloudflare em vez de resultados (regra do scanner-comc)."""
    if not html:
        return True
    return not ("cardexplorer" in html or "searchResultsStats" in html)


class COMCAvailability:
    """Menor listagem plausível EX-NM ungraded EN na COMC, via Firecrawl."""

    def __init__(self, api_key: str):
        self._key = api_key

    def _fetch(self, url: str) -> str:
        payload = {"url": url, "formats": ["rawHtml"],
                   "location": {"country": "US", "languages": ["en-US"]},
                   "proxy": "stealth", "onlyMainContent": False,
                   "waitFor": 12000}
        last: Exception | None = None
        for attempt in range(RETRIES + 1):
            if attempt:
                time.sleep(2 * attempt)
            try:
                r = requests.post(
                    FIRECRAWL_URL, json=payload, timeout=TIMEOUT_S,
                    headers={"Authorization": f"Bearer {self._key}"})
            except requests.RequestException as exc:
                last = RuntimeError(f"Firecrawl rede: {exc}")
                continue
            if r.status_code != 200:
                last = RuntimeError(f"Firecrawl HTTP {r.status_code}")
                if r.status_code in (402, 401):   # sem créditos/key: não insistir
                    break
                continue
            env = r.json()
            if not env.get("success", True):
                last = RuntimeError(f"Firecrawl: {env.get('error') or 'falha'}")
                continue
            data = env.get("data", env)
            html = data.get("rawHtml") or data.get("html") or ""
            if _is_challenge(html):
                last = RuntimeError("COMC atrás de challenge Cloudflare")
                continue
            return html
        raise last

    def cheapest(self, name: str, number: str,
                 ref_usd: Optional[float] = None) -> dict:
        """{'usd','qty','url','status','junk_skipped'} — menor listagem
        plausível. status nunca silencioso."""
        try:
            html = self._fetch(comc_search_url(name))
        except RuntimeError as exc:
            return {"status": f"erro: {exc}"}
        listings = parse_comc_page(html)
        if not listings:
            return {"status": "carta não encontrada na COMC"}
        base = _base_name(name)
        want = _clean_number(number)
        best, junk = None, 0
        for l in listings:
            if l["graded"]:
                continue
            if l["condition"].lower() not in NM_CONDITION_ALLOW:
                continue
            if _clean_number(l["number"]) != want:
                continue
            if base and base not in _norm(l["name"]):
                continue
            if any(mk in _norm(l["set"]) for mk in NON_EN_MARKERS):
                continue
            if ref_usd and ref_usd > 0 and l["price"] < SUSPECT_RATIO * ref_usd:
                junk += 1
                continue
            if best is None or l["price"] < best["usd"]:
                best = {"usd": l["price"], "qty": l["qty"], "url": l["url"],
                        "status": "ok"}
        if best:
            best["junk_skipped"] = junk
            return best
        if junk:
            return {"status": f"só listagens-lixo ({junk} < 50% da ref)"}
        return {"status": "sem listagem EX-NM EN no nº"}
