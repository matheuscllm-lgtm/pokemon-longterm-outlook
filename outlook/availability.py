"""Disponibilidade por plataforma — onde a carta está acessível AGORA.

Para cada carta do top-N do ranking de longo prazo, responde: em qual
plataforma ela está disponível e por quanto, com link de acesso direto.

Cobertura honesta por plataforma (2026-07):
  - CardTrader  → PREÇO REAL via API oficial (menor oferta EN+NM não-graded)
                  + link direto da carta. Token CT_JWT lido da env var CT_JWT
                  (qualquer ambiente, inclusive nuvem) ou do .env do repo
                  card-trader-scanner (PC). Nunca logado/impresso.
  - TCGPlayer   → preço market de referência (já vem do ranking/tcgcsv) +
                  menor anúncio (lowPrice, condição NÃO filtrada — informativo)
                  + link direto do produto.
  - eBay        → SEM preço automatizado (Browse API exige keys que o
                  operador ainda não criou; scrape = 403). Link de busca.
  - COMC        → SEM preço automatizado (site exige navegador real/headful
                  pra passar o Cloudflare). Link de busca.
  - Liga Pokémon→ SEM preço automatizado (Cloudflare; coletor é headful e
                  lento demais pra 50 cartas ad-hoc). Link de busca.
  - MYP         → SEM preço automatizado AQUI: a API (mypcards.com/api/v1)
                  existe, mas está atrás de challenge Cloudflare — provado
                  2026-07 do ambiente nuvem (403 + TLS reset mesmo via
                  curl_cffi/proxy). Cobertura automatizada do MYP é do
                  scanner MYP da frota (PC). O site também não filtra por
                  querystring (testado ?busca/?q/?nome/?s) → link de busca
                  via Google site-restrito.

NUNCA inventa preço: plataforma sem coleta automatizada aparece como link
pra conferência manual, explicitamente.
"""
from __future__ import annotations

import os
import time
import unicodedata
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import requests

from .sets import strip_era_prefix

CT_BASE = "https://api.cardtrader.com/api/v2"
CT_ENV_PATH = Path(r"C:\Users\mathe\card-trader-scanner\.env")
CT_POKEMON_GAME_ID = 5
CT_RETRIES = 3
REQUEST_DELAY_S = 0.55
TIMEOUT_S = 30
FX_API = "https://open.er-api.com/v6/latest/USD"
FX_EUR_USD_FALLBACK = 1.08   # usado só se a API de câmbio falhar (documentado)

# BOM/zero-width num segredo crasham o header HTTP (latin-1) e o run vem
# "verde mas vazio" — .strip() comum NÃO remove BOM. Sanitização explícita.
_INVISIBLE_CHARS = "\ufeff\u200b\u200c\u200d\u200e\u200f"


def _clean_secret(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    cleaned = raw.strip().strip(_INVISIBLE_CHARS).strip()
    return cleaned or None


def load_ct_jwt(env_path: Path = CT_ENV_PATH) -> Optional[str]:
    """CT_JWT da env var (qualquer ambiente) ou do .env do repo CardTrader (PC).

    A env var tem precedência — é o único caminho viável fora do PC do
    operador (nuvem/CI). O valor NUNCA é impresso/logado.
    """
    from_env = _clean_secret(os.environ.get("CT_JWT"))
    if from_env:
        return from_env
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().lstrip(_INVISIBLE_CHARS).startswith("CT_JWT="):
                return _clean_secret(line.split("=", 1)[1])
    except OSError:
        pass
    return None


def _norm(text: str) -> str:
    nfkd = unicodedata.normalize("NFD", text or "")
    out = "".join(c for c in nfkd if not unicodedata.combining(c))
    return out.lower().strip()


def _strip_era_prefix(set_name: str) -> str:
    """'SWSH07: Evolving Skies' → 'evolving skies' (nomes CT não têm o prefixo).

    Tira o prefixo com o helper compartilhado (outlook.sets) e normaliza
    (caixa/acento) pro match com os nomes de expansão do CardTrader.
    """
    return _norm(strip_era_prefix(set_name))


def _clean_number(num: str) -> str:
    return (num or "").split("/")[0].strip().lstrip("0") or "0"


def _base_name(card_name: str) -> str:
    """'Venusaur ex (Alternate Full Art)' → 'venusaur ex' (sem descritores)."""
    out, depth = [], 0
    for ch in card_name or "":
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return " ".join(_norm("".join(out)).split())


# Abaixo desta fração da referência market, um "achado" CT é quase sempre
# match de carta/variante errada — regra da frota: rotular suspeito, nunca
# escolher o número que confirma o deal.
SUSPECT_RATIO = 0.5


def verdict_nm_en(ct_usd: Optional[float], market_usd: float,
                  ct_status: str = "", has_ct: bool = True) -> str:
    """Veredito 'Mais barato NM-EN' — honesto por construção.

    Compara APENAS fontes com filtro NM+EN real (hoje: CardTrader) contra a
    referência market do TCGPlayer. CT bom demais (< SUSPECT_RATIO da ref)
    vira '⚠️ suspeito', nunca vencedor.
    """
    if ct_usd is None:
        if not has_ct:
            return "n/d — sem fonte NM-EN ao vivo (defina CT_JWT)"
        return f"n/d — CT: {ct_status}; confira os links"
    if market_usd > 0 and ct_usd < SUSPECT_RATIO * market_usd:
        off = (1 - ct_usd / market_usd) * 100
        return (f"⚠️ suspeito — CT US$ {ct_usd:.2f} está {off:.0f}% abaixo da "
                f"ref (provável variante/carta errada no match; confira o link CT)")
    delta = abs(ct_usd - market_usd) / market_usd * 100 if market_usd > 0 else 0.0
    if ct_usd < market_usd:
        return f"**CardTrader** US$ {ct_usd:.2f} ({delta:.0f}% abaixo da ref TCG)"
    # CT acima da ref: NÃO declara "TCGPlayer" vencedor — a ref é média de
    # vendas, não um anúncio comprável (auditoria 2026-07-13). Só constata.
    return (f"nenhum anúncio NM-EN abaixo da ref — CT {delta:.0f}% acima "
            f"(ref TCG = média de vendas, não anúncio)")


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
        # Retry curto: a API do CT devolve erro TRANSIENTE ocasional (caso
        # real observado: um 401 isolado em /blueprints/export que sumiu no
        # request seguinte) — sem retry, a linha degrada pra "erro" e o
        # relatório oscila entre runs. Erro persistente continua reportado.
        last: Exception | None = None
        for attempt in range(CT_RETRIES):
            time.sleep(REQUEST_DELAY_S * (attempt + 1))
            try:
                r = requests.get(f"{CT_BASE}{path}", headers=self.headers,
                                 params=params, timeout=TIMEOUT_S)
            except requests.RequestException as exc:
                last = RuntimeError(f"CT rede em {path}: {exc}")
                continue
            if r.status_code == 200:
                return r.json()
            last = RuntimeError(f"CT HTTP {r.status_code} em {path}")
        raise last

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

    # Nomes de set onde o fuzzy erra DE PROPÓSITO conhecido (tcgcsv → CT).
    # Casos provados em runs reais:
    #   - "Scarlet & Violet 151" caía no set base "Scarlet & Violet" via
    #     contains — o nome real no CT é só "151" (code mew).
    #   - "SV01/SWSH01: ... Base Set" caía no "Base Set" WotC de 1999 (code
    #     bs) — "base set" ⊆ alvo e o WotC vinha primeiro na lista. Nº que
    #     coincidisse casaria carta ERRADA em silêncio; nº alto saía "carta
    #     não encontrada" (run 2026-07-13: 4 linhas).
    #   - "Pokemon GO" caía no "Pokémon GO Enhanced Expansion Pack" (set
    #     JAPONÊS s10b) → "sem oferta EN+NM" enganoso em 5 linhas; o set
    #     internacional no CT chama "Pokémon TCG: Pokémon GO" (code pkmgo).
    SET_NAME_OVERRIDES = {
        "scarlet & violet 151": "151",
        "scarlet & violet base set": "scarlet & violet",
        "sword & shield base set": "sword & shield",
        "pokemon go": "pokemon tcg: pokemon go",
    }

    def find_expansion_id(self, set_name: str) -> Optional[int]:
        if self._expansions is None:
            data = self._get("/expansions")
            self._expansions = [e for e in data
                                if e.get("game_id") == CT_POKEMON_GAME_ID]
        target = _strip_era_prefix(set_name)
        override = self.SET_NAME_OVERRIDES.get(target)
        if override:
            for e in self._expansions:
                if _norm(e.get("name", "")) == override:
                    return e["id"]
            return None                      # override sem alvo: melhor n/d que set errado
        for e in self._expansions:           # match exato primeiro
            if _norm(e.get("name", "")) == target:
                return e["id"]
        # Contains RANQUEADO (não first-hit, que dependia da ordem da API e
        # produzia os falsos matches acima):
        #   1) nome CT contido no alvo → o mais LONGO vence (mais específico:
        #      "crown zenith" ⊃ alvo "crown zenith: galarian gallery" ganha
        #      de um hipotético nome curto genérico);
        #   2) alvo contido no nome CT → o mais CURTO vence (menos sufixo
        #      estranho: "pokemon tcg: pokemon go" ganha de "pokemon go
        #      enhanced expansion pack").
        contained = [e for e in self._expansions
                     if _norm(e.get("name", "")) and _norm(e.get("name", "")) in target]
        if contained:
            return max(contained, key=lambda e: len(_norm(e.get("name", ""))))["id"]
        containing = [e for e in self._expansions
                      if target and target in _norm(e.get("name", ""))]
        if containing:
            return min(containing, key=lambda e: len(_norm(e.get("name", ""))))["id"]
        return None

    def _blueprint_for(self, expansion_id: int, number: str,
                       card_name: str = "") -> Optional[dict]:
        """Blueprint pelo número de coleção, desambiguado pelo NOME.

        Sets com blueprints duplicados no mesmo número (promos, variantes)
        faziam o match número-só devolver a carta ERRADA — e o preço vinha
        absurdo. Com card_name, entre os candidatos do número vence o que
        contém o nome-base da carta; sem candidato com nome batendo, cai no
        primeiro do número (o veredito ainda tem o gate de suspeito).
        """
        if expansion_id not in self._blueprints:
            self._blueprints[expansion_id] = self._get(
                "/blueprints/export", expansion_id=expansion_id)
        want = _clean_number(number)
        candidates = []
        for bp in self._blueprints[expansion_id]:
            fixed = bp.get("fixed_properties") or {}
            bp_num = fixed.get("collector_number") or bp.get("version") or ""
            if _clean_number(str(bp_num)) == want:
                candidates.append(bp)
        if not candidates:
            return None
        base = _base_name(card_name)
        if base:
            for bp in candidates:
                if base in _norm(bp.get("name", "")):
                    return bp
        return candidates[0]

    def _max_numeric_number(self, expansion_id: int) -> Optional[int]:
        """Maior collector number NUMÉRICO do set casado (pros de letra: TG12
        etc. ficam de fora). Usa o export já cacheado pelo _blueprint_for."""
        best: Optional[int] = None
        for bp in self._blueprints.get(expansion_id, []):
            fixed = bp.get("fixed_properties") or {}
            num = _clean_number(str(fixed.get("collector_number")
                                    or bp.get("version") or ""))
            if num.isdigit():
                n = int(num)
                if best is None or n > best:
                    best = n
        return best

    def cheapest(self, set_name: str, number: str, card_name: str = "",
                 ref_usd: Optional[float] = None) -> dict:
        """{'usd', 'qty', 'url', 'status', 'junk_skipped'} — menor oferta
        EN+NM não-graded PLAUSÍVEL.

        Marketplace tem anúncio-lixo (caso real: Venusaur ex SIR por R$ 0,89
        com as ofertas reais a ~R$ 776) — com ref_usd, anúncios abaixo de
        SUSPECT_RATIO×ref são pulados e CONTADOS em junk_skipped, e vence a
        oferta plausível mais barata. Sem ref_usd, comportamento antigo (o
        gate do veredito segue de backstop).

        status: 'ok' | 'set não mapeado' | 'carta não encontrada' (com o
                sufixo 'provável set errado' quando o nº pedido excede a
                faixa numérica do set casado) | 'sem oferta EN+NM' |
                'só anúncios-lixo (N < 50% da ref)' | 'erro: ...' —
                nunca silencioso.
        """
        try:
            exp_id = self.find_expansion_id(set_name)
            if not exp_id:
                return {"status": "set não mapeado no CT"}
            bp = self._blueprint_for(exp_id, number, card_name)
            if not bp:
                # Autodetecção de set errado (auditoria 2026-07-13): quando o
                # nº pedido está ACIMA da faixa numérica do set casado, o
                # provável não é "carta rara demais" — é o match de expansão
                # ter caído noutro set (classe de bug que produziu 9% do
                # relatório em n/d antes dos overrides). Sinaliza explícito
                # em vez do genérico "carta não encontrada".
                want = _clean_number(number)
                max_num = self._max_numeric_number(exp_id)
                if want.isdigit() and max_num and int(want) > max_num:
                    return {"status": (f"carta não encontrada — nº {want} > "
                                       f"máx {max_num} do set casado no CT "
                                       f"(provável set errado; confira)")}
                return {"status": "carta não encontrada no CT"}
            listings = self._get("/marketplace/products", blueprint_id=bp["id"],
                                 language="en")
            if isinstance(listings, dict):
                listings = [l for ls in listings.values() for l in ls]
            best, junk = None, 0
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
                if ref_usd and ref_usd > 0 and usd < SUSPECT_RATIO * ref_usd:
                    junk += 1
                    continue
                if best is None or usd < best["usd"]:
                    best = {"usd": usd, "qty": l.get("quantity"),
                            "url": f"https://www.cardtrader.com/cards/{bp['id']}",
                            "status": "ok", "junk_skipped": junk}
            if best:
                best["junk_skipped"] = junk
                return best
            if junk:
                return {"status": f"só anúncios-lixo ({junk} < 50% da ref)"}
            return {"status": "sem oferta EN+NM"}
        except RuntimeError as exc:
            return {"status": f"erro: {exc}"}


# ── Links de busca direta (plataformas sem coleta automatizada) ──────────────
def ebay_url(name: str, set_name: str, number: str) -> str:
    q = quote_plus(f"pokemon {name} {_clean_number(number)} {_strip_era_prefix(set_name)}")
    return f"https://www.ebay.com/sch/i.html?_nkw={q}"


# Categoria "CCG Individual Cards" do eBay — a mesma que ebay_availability.py
# usa na Browse API; sem ela a busca traz lote, playmat e caixa junto.
EBAY_CCG_SINGLES_CATEGORY = "183454"


def ebay_psa10_url(name: str, set_name: str, number: str) -> str:
    """Link de COMPRA no eBay já filtrado em PSA 10, do mais barato pro mais caro.

    Mesma query da coleta (`ebay_availability.cheapest`): nome sem o qualificador
    entre parênteses + número limpo + set sem prefixo de era — o número é o que
    identifica a variante, e o slab do PSA traz o número no título. Acrescenta
    "psa 10" e fixa três parâmetros do eBay:

      _sacat=183454  categoria CCG Individual Cards (corta lote/acessório)
      LH_BIN=1       só Buy It Now (espelha buyingOptions:{FIXED_PRICE} da API)
      _sop=15        ordena por preço + frete, menor primeiro

    É um link de BUSCA, não de um anúncio específico: sem EBAY_CLIENT_ID/SECRET
    não há como resolver o menor anúncio real, e este projeto não inventa preço.
    A busca é texto — pode trazer PSA 10 de outra variante do mesmo número; a
    conferência final é no anúncio.
    """
    q = quote_plus(" ".join(
        f"pokemon {_base_name(name)} {_clean_number(number)} "
        f"{_strip_era_prefix(set_name)} psa 10".split()))
    return (f"https://www.ebay.com/sch/i.html?_nkw={q}"
            f"&_sacat={EBAY_CCG_SINGLES_CATEGORY}&LH_BIN=1&_sop=15")


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
