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


def _strip_number_suffix(name: str, full_number: str) -> str:
    """Tira o sufixo ' - 008/159' que o TCGPlayer anexa a alguns nomes.

    A coluna Nº da tabela já mostra esse número; repetido no nome é só ruído
    (e desalinha visualmente as linhas que não têm o sufixo). Corta SÓ quando o
    nome termina exatamente em ' - <Number>' — combinação literal, sem
    heurística frouxa que arriscaria cortar um nome que use ' - ' de verdade.
    """
    suffix = f" - {full_number}"
    if full_number and name.endswith(suffix):
        return name[: -len(suffix)].rstrip()
    return name


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
        raw_number = str(ext.get("Number") or "").strip()
        number = raw_number.split("/")[0].strip()
        cards.append({
            "id": str(prod["productId"]),
            "name": _strip_number_suffix(prod.get("name", ""), raw_number),
            "number": number,
            "rarity": rarity,
            "_market_usd": best_by_pid.get(prod["productId"]),
            "_url": prod.get("url") or "",
        })
    return cards


def best_market_usd(card: dict) -> Optional[float]:
    return card.get("_market_usd")


def tcgplayer_url(card: dict) -> str:
    return card.get("_url") or ""
