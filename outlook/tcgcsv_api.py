"""Fonte tcgcsv.com — dumps diários do catálogo/preços do TCGPlayer.

Por que existe: o pokemontcg.io oscila (504/timeout eram frequentes em
2026-06) e os runners de nuvem nem o alcançam. O tcgcsv serve o MESMO
conteúdo de preço (marketPrice TCGPlayer, atualizado 1x/dia) em arquivos
estáticos — 2 requests por set, estável e rápido. É a fonte DEFAULT.

Regras de uso do site: identificar a aplicação no User-Agent (sem isso o
servidor responde 401 com um recado do mantenedor).

Estrutura: /tcgplayer/3/groups → sets ("groups", com publishedOn);
/tcgplayer/3/{groupId}/products → cartas+selados (cartas têm extendedData
Rarity/Number); /tcgplayer/3/{groupId}/prices → marketPrice por variante
(subTypeName; ignoramos "Reverse Holofoil").
"""
from __future__ import annotations

import re
import time
from datetime import date
from typing import Optional

import requests

BASE = "https://tcgcsv.com/tcgplayer/3"   # 3 = categoria Pokémon
HEADERS = {"User-Agent": "pokemon-longterm-outlook/0.1"}
TIMEOUT_S = 60
RETRIES = 3

# Eras suportadas → (prefixo regex dos grupos numerados, série "bonita")
ERA_PREFIXES = {
    "Scarlet & Violet": r"^SV[0-9: ]",
    "Sword & Shield": r"^SWSH[0-9: ]",
    "Mega Evolution": r"^ME[0-9: ]",
}
# Sets especiais SEM prefixo de era no nome (mapeados à mão → série).
SPECIAL_SETS = {
    "Shining Fates": "Sword & Shield",
    "Shining Fates: Shiny Vault": "Sword & Shield",
    "Champion's Path": "Sword & Shield",
    "Celebrations": "Sword & Shield",
    "Celebrations: Classic Collection": "Sword & Shield",
    "Pokemon GO": "Sword & Shield",
}


def _get_json(url: str) -> dict:
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT_S)
            if r.status_code == 200:
                return r.json()
            last = RuntimeError(f"HTTP {r.status_code} em {url}: {r.text[:120]}")
        except requests.RequestException as exc:
            last = exc
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"tcgcsv indisponível: {last}")


def fetch_sets(series_list: list[str], today: date | None = None) -> list[dict]:
    """Sets das eras pedidas, no formato que o scoring espera.

    Exclui: promos (datas heterogêneas) e sets ainda não lançados (presale).
    """
    today = today or date.today()
    groups = _get_json(f"{BASE}/groups")["results"]
    out: list[dict] = []
    for g in groups:
        name = g.get("name", "")
        if "Promo" in name:
            continue
        series = SPECIAL_SETS.get(name)
        if series is None:
            for s, pat in ERA_PREFIXES.items():
                if s in series_list and re.match(pat, name):
                    series = s
                    break
        if series is None or series not in series_list:
            continue
        release = (g.get("publishedOn") or "")[:10]
        if not release or date.fromisoformat(release) > today:
            continue  # presale/futuro: ainda nem existe supply
        out.append({"id": str(g["groupId"]), "name": name,
                    "series": series, "releaseDate": release})
    return out


def fetch_cards_with_prices(group_id: str) -> list[dict]:
    """Cartas do set já com o melhor preço market embutido (USD).

    Devolve dicts no formato do scoring: id/name/number/rarity + _market_usd
    + _url. Produtos sem extendedData.Rarity (selados, lotes) ficam de fora;
    cartas sem preço market também (contadas pelo chamador via diferença).
    """
    prods = _get_json(f"{BASE}/{group_id}/products")["results"]
    prices = _get_json(f"{BASE}/{group_id}/prices")["results"]
    best_by_pid: dict[int, float] = {}
    for p in prices:
        if "reverse" in (p.get("subTypeName") or "").lower():
            continue
        m = p.get("marketPrice")
        if isinstance(m, (int, float)) and m > 0:
            pid = p["productId"]
            best_by_pid[pid] = max(best_by_pid.get(pid, 0.0), float(m))
    cards: list[dict] = []
    for prod in prods:
        ext = {e["name"]: e.get("value") for e in (prod.get("extendedData") or [])}
        rarity = ext.get("Rarity")
        if not rarity:
            continue  # não é carta avulsa
        number = str(ext.get("Number") or "").split("/")[0].strip()
        cards.append({
            "id": str(prod["productId"]),
            "name": prod.get("name", ""),
            "number": number,
            "rarity": rarity,
            "_market_usd": best_by_pid.get(prod["productId"]),
            "_url": prod.get("url") or "",
        })
    return cards


# Tipos de produto selado reconhecidos (1ª regra que casar vence). Lotes
# (case/display/multipacks) ficam de fora: são N unidades e distorcem o preço.
SEALED_TYPES = [
    ("Booster Box", ("booster box",)),
    ("Booster Bundle", ("booster bundle",)),
    ("Elite Trainer Box", ("elite trainer",)),
    ("Booster Pack", ("booster pack",)),
    ("Mini Tin", ("mini tin",)),
    ("Build & Battle", ("build & battle", "build and battle")),
    ("Collection", ("collection",)),
    ("Tin", ("tin",)),
]
_SEALED_EXCLUDE = ("case", "display", "[set of", "-pack", " pack of", "lot")


def _sealed_type(name: str) -> Optional[str]:
    low = name.lower()
    if any(k in low for k in _SEALED_EXCLUDE):
        return None
    for label, keys in SEALED_TYPES:
        if any(k in low for k in keys):
            return label
    return None


def fetch_sealed_with_prices(group_id: str) -> list[dict]:
    """Produtos SELADOS do set com preço market (USD) e tipo classificado.

    Espelha fetch_cards_with_prices, mas pega o que NÃO é carta avulsa (sem
    extendedData.Rarity) e casa um tipo de SKU conhecido (ETB/Box/Bundle/Tin...).
    Devolve dicts no formato que outlook.sealed espera: id/name/product_type +
    _market_usd + _url.
    """
    prods = _get_json(f"{BASE}/{group_id}/products")["results"]
    prices = _get_json(f"{BASE}/{group_id}/prices")["results"]
    best_by_pid: dict[int, float] = {}
    for p in prices:
        if "reverse" in (p.get("subTypeName") or "").lower():
            continue
        m = p.get("marketPrice")
        if isinstance(m, (int, float)) and m > 0:
            pid = p["productId"]
            best_by_pid[pid] = max(best_by_pid.get(pid, 0.0), float(m))
    out: list[dict] = []
    for prod in prods:
        ext = {e["name"]: e.get("value") for e in (prod.get("extendedData") or [])}
        if ext.get("Rarity"):
            continue  # é carta avulsa, não selado
        ptype = _sealed_type(prod.get("name", ""))
        if ptype is None:
            continue
        out.append({
            "id": str(prod["productId"]),
            "name": prod.get("name", ""),
            "product_type": ptype,
            "_market_usd": best_by_pid.get(prod["productId"]),
            "_url": prod.get("url") or "",
        })
    return out


def best_market_usd(card: dict) -> Optional[float]:
    return card.get("_market_usd")


def tcgplayer_url(card: dict) -> str:
    return card.get("_url") or ""
