"""Disponibilidade por plataforma — onde a carta está acessível AGORA.

Para cada carta do top-N do ranking de longo prazo, responde: em qual
plataforma ela está disponível e por quanto, com link de acesso direto.

Cobertura honesta por plataforma (2026-06):
  - CardTrader  → PREÇO REAL via API oficial (menor oferta EN+NM não-graded)
                  + link direto da carta. Token CT_JWT lido do .env do repo
                  card-trader-scanner (nunca logado/impresso).
  - TCGPlayer   → preço market de referência (já vem do ranking/tcgcsv)
                  + link direto do produto.
  - eBay        → SEM preço automatizado (Browse API exige keys que o
                  operador ainda não criou; scrape = 403). Link de busca.
  - COMC        → SEM preço automatizado (site exige navegador real/headful
                  pra passar o Cloudflare). Link de busca.
  - Liga Pokémon→ SEM preço automatizado (Cloudflare; coletor é headful e
                  lento demais pra 50 cartas ad-hoc). Link de busca.
  - MYP         → SEM preço automatizado E SEM busca por URL (o site só
                  filtra via JavaScript; testado ?busca/?q/?nome/?s — nenhum
                  filtra). Link de busca via Google site-restrito.

NUNCA inventa preço: plataforma sem coleta automatizada aparece como link
pra conferência manual, explicitamente.
"""
from __future__ import annotations

import time
import unicodedata
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import requests

CT_BASE = "https://api.cardtrader.com/api/v2"
CT_ENV_PATH = Path(r"C:\Users\mathe\card-trader-scanner\.env")
CT_POKEMON_GAME_ID = 5
REQUEST_DELAY_S = 0.55
TIMEOUT_S = 30
FX_API = "https://open.er-api.com/v6/latest/USD"
FX_EUR_USD_FALLBACK = 1.08   # usado só se a API de câmbio falhar (documentado)


def load_ct_jwt(env_path: Path = CT_ENV_PATH) -> Optional[str]:
    """Lê CT_JWT do .env do repo CardTrader. O valor NUNCA é impresso."""
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("CT_JWT="):
                return line.split("=", 1)[1].strip() or None
    except OSError:
        pass
    return None


def _norm(text: str) -> str:
    nfkd = unicodedata.normalize("NFD", text or "")
    out = "".join(c for c in nfkd if not unicodedata.combining(c))
    return out.lower().strip()


def _strip_era_prefix(set_name: str) -> str:
    """'SWSH07: Evolving Skies' → 'evolving skies' (nomes CT não têm o prefixo)."""
    if ":" in set_name:
        prefix, rest = set_name.split(":", 1)
        if len(prefix) <= 8:          # SV08 / SWSH07 / ME03 / SV...
            return _norm(rest)
    return _norm(set_name)


def _clean_number(num: str) -> str:
    return (num or "").split("/")[0].strip().lstrip("0") or "0"


class CTAvailability:
    """Menor oferta EN+NM não-graded por carta, via API oficial do CardTrader."""

    def __init__(self, jwt: str):
        self.headers = {"Authorization": f"Bearer {jwt}",
                        "Accept": "application/json",
                        "User-Agent": "pokemon-longterm-outlook/0.2"}
        self._expansions: list[dict] | None = None
        self._blueprints: dict[int, list[dict]] = {}
        self._usd_rates: dict[str, float] | None = None

    def _get(self, path: str, **params):
        time.sleep(REQUEST_DELAY_S)
        r = requests.get(f"{CT_BASE}{path}", headers=self.headers,
                         params=params, timeout=TIMEOUT_S)
        if r.status_code != 200:
            raise RuntimeError(f"CT HTTP {r.status_code} em {path}")
        return r.json()

    def _to_usd(self, cents: int, currency: str) -> Optional[float]:
        amount = cents / 100.0
        cur = (currency or "EUR").upper()
        if cur == "USD":
            return amount
        if self._usd_rates is None:
            try:
                j = requests.get(FX_API, timeout=15).json()
                self._usd_rates = j.get("rates") or {}
            except requests.RequestException:
                self._usd_rates = {}
        rate = self._usd_rates.get(cur)
        if rate and rate > 0:
            return amount / rate
        if cur == "EUR":
            return amount * FX_EUR_USD_FALLBACK
        return None

    def find_expansion_id(self, set_name: str) -> Optional[int]:
        if self._expansions is None:
            data = self._get("/expansions")
            self._expansions = [e for e in data
                                if e.get("game_id") == CT_POKEMON_GAME_ID]
        target = _strip_era_prefix(set_name)
        for e in self._expansions:           # match exato primeiro
            if _norm(e.get("name", "")) == target:
                return e["id"]
        for e in self._expansions:           # depois, contains (mais frouxo)
            n = _norm(e.get("name", ""))
            if target in n or n in target:
                return e["id"]
        return None

    def _blueprint_for(self, expansion_id: int, number: str) -> Optional[dict]:
        if expansion_id not in self._blueprints:
            self._blueprints[expansion_id] = self._get(
                "/blueprints/export", expansion_id=expansion_id)
        want = _clean_number(number)
        for bp in self._blueprints[expansion_id]:
            fixed = bp.get("fixed_properties") or {}
            bp_num = fixed.get("collector_number") or bp.get("version") or ""
            if _clean_number(str(bp_num)) == want:
                return bp
        return None

    def cheapest(self, set_name: str, number: str) -> dict:
        """{'usd', 'qty', 'url', 'status'} — menor oferta EN+NM não-graded.

        status: 'ok' | 'set não mapeado' | 'carta não encontrada' |
                'sem oferta EN+NM' | 'erro: ...' — nunca silencioso.
        """
        try:
            exp_id = self.find_expansion_id(set_name)
            if not exp_id:
                return {"status": "set não mapeado no CT"}
            bp = self._blueprint_for(exp_id, number)
            if not bp:
                return {"status": "carta não encontrada no CT"}
            listings = self._get("/marketplace/products", blueprint_id=bp["id"],
                                 language="en")
            if isinstance(listings, dict):
                listings = [l for ls in listings.values() for l in ls]
            best = None
            for l in listings:
                props = l.get("properties_hash") or {}
                if props.get("condition") != "Near Mint":
                    continue
                if (props.get("pokemon_language") or "").lower() != "en":
                    continue
                if l.get("graded"):
                    continue
                price = l.get("price") or {}
                cents = price.get("cents")
                if not isinstance(cents, int):
                    continue
                usd = self._to_usd(cents, price.get("currency", "EUR"))
                if usd is None:
                    continue
                if best is None or usd < best["usd"]:
                    best = {"usd": usd, "qty": l.get("quantity"),
                            "url": f"https://www.cardtrader.com/cards/{bp['id']}",
                            "status": "ok"}
            return best or {"status": "sem oferta EN+NM"}
        except RuntimeError as exc:
            return {"status": f"erro: {exc}"}


# ── Links de busca direta (plataformas sem coleta automatizada) ──────────────
def ebay_url(name: str, set_name: str, number: str) -> str:
    q = quote_plus(f"pokemon {name} {_clean_number(number)} {_strip_era_prefix(set_name)}")
    return f"https://www.ebay.com/sch/i.html?_nkw={q}"


def comc_url(name: str) -> str:
    return f"https://www.comc.com/Cards/Pokemon,sq,{quote_plus(name)}"


def liga_url(name: str) -> str:
    return ("https://www.ligapokemon.com.br/?view=cards/search&card="
            + quote_plus(name))


def myp_url(name: str) -> str:
    # MYP não tem busca por querystring (filtro é client-side JS); a forma
    # confiável de "link direto" é a busca Google restrita ao site.
    return ("https://www.google.com/search?q="
            + quote_plus(f"site:mypcards.com/pokemon/produto {name}"))
