"""Preço e liquidez PSA 10 via PriceCharting — insumo do modo graded do score.

POR QUE ESTE MÓDULO EXISTE
--------------------------
O score de longo prazo nasceu com o componente de Preço calibrado em faixas de
carta CRUA (raw): a lógica era "espaço pra crescer com liquidez". Para quem só
compra carta GRADUADA (PSA 10), essa é a régua errada — o preço que importa é o
do slab, e o mercado relevante é o de PSA 10, não o de carta solta.

Este módulo coleta os dois números que o modo graded precisa, por carta:
  - preço PSA 10 (US$) — o "preço justo" do slab, derivado de vendas REAIS
    agregadas pelo PriceCharting;
  - vendas/mês de PSA 10 — a liquidez daquele slab (um preço de tabela num
    mercado que vende uma vez por trimestre não é preço realizável).

FONTE E HONESTIDADE
-------------------
Mesma fonte que este repo já usa para a tendência (`outlook/pricecharting.py`):
páginas públicas do PriceCharting. Não é fonte nova, é um campo novo da MESMA
página. Qualquer falha (HTTP, sem match confiável, parse) devolve status
explícito e valor None — **nunca** inventa preço nem liquidez, e o modo graded
trata "sem dado" como "sem dado", não como zero.

O match carta→produto é por BUSCA de texto. Guard herdado da coleta: o número
da carta TEM que aparecer no título/URL do produto; sem isso devolvemos
"sem match confiável" em vez de arriscar a carta errada (a lição de falso match
que já custou caro na frota).
"""
from __future__ import annotations

import hashlib
import html as html_mod
import json
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote

from .availability import _base_name, _clean_number
from .pricecharting import HEADERS, SEARCH, SLEEP_S, TIMEOUT_S
from .sets import strip_era_prefix

# Rótulo do PSA 10 na tabela "Full Price Guide" (#full-prices) do PriceCharting.
FULL_TABLE_PSA10_LABEL = "PSA 10"

# Na tabela principal (#price_data) as colunas de preço têm ids herdados de
# video game; o do PSA 10 é "manual_only_price". As células de VOLUME aparecem
# na MESMA ordem das colunas de preço — por isso a ordem abaixo importa.
MAIN_TABLE_GRADE_ORDER = (
    "used_price",         # Ungraded (raw)
    "complete_price",     # Grade 7
    "new_price",          # Grade 8
    "graded_price",       # Grade 9 (PSA 9)
    "box_only_price",     # Grade 9.5
    "manual_only_price",  # PSA 10
)
PSA10_COLUMN_INDEX = MAIN_TABLE_GRADE_ORDER.index("manual_only_price")

_MONEY_RE = r"\$?([\d,]+\.\d{2})"

# ── Pop report (modo low pop) ────────────────────────────────────────────────
# A MESMA página de produto traz o censo de população graduada embutido no
# HTML (aba "POP Report"), como um objeto JS: notas 1..10, PSA e CGC:
#   VGPC.pop_data = {"cgc":[0,0,0,0,3,0,2,23,95,295],"psa":[0,0,0,2,6,10,9,102,1095,2595]};
# Provado em 2026-09-21 numa sonda de 30 cartas (vintage/SWSH/SV): 29/30 com
# pop, sem navegador, ~3s/carta. O censo é MENSAL ("population census updated
# monthly") — velocidade de pop exige duas leituras em datas diferentes.
_POP_DATA_RE = re.compile(r"VGPC\.pop_data\s*=\s*(\{.*?\})\s*;", re.S)
# O TCGPlayer ID vem num link de afiliado com a URL do produto URL-encoded:
#   ...?u=https%3A%2F%2Fwww.tcgplayer.com%2Fproduct%2F676088%2F-...
_TCG_PID_RE = re.compile(r"tcgplayer\.com(?:/|%2F)product(?:/|%2F)(\d+)")
# Resultados da busca (quando a query NÃO redireciona direto pro produto):
# linhas da tabela #games_table, link ABSOLUTO em td.title; o título traz o
# qualificador de variante entre colchetes ("Charizard [1st Edition] #4").
_SEARCH_ROW_RE = re.compile(
    r'<td class="title">\s*<a href="(https://www\.pricecharting\.com/game/[^"]+)"'
    r'[^>]*>\s*(.*?)</a>', re.S)

# Cache em disco (gitignored): 1 arquivo por carta, válido por CACHE_TTL_DAYS.
# Justificativa: o pool do modo low pop pode ter centenas/milhares de cartas
# (~3s cada); o censo é mensal e o preço PSA 10 muda devagar — reconsultar todo
# dia é desperdício e maltrata o site.
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache" / "pricecharting"
CACHE_TTL_DAYS = 1


def _money(text: str) -> float | None:
    try:
        return float(text.replace(",", "").replace("$", ""))
    except (ValueError, AttributeError):
        return None


def parse_psa10_price(body: str) -> float | None:
    """Preço PSA 10 (US$) da página de produto, ou None se a página não traz.

    Tenta a tabela "Full Price Guide" (rótulo textual, mais estável) e cai na
    tabela principal (id `manual_only_price`) quando a primeira não existe.
    """
    m = re.search(r'id="full-prices">.*?<table>(.*?)</table>', body, re.S)
    if m:
        rows = re.findall(
            r"<tr>\s*<td>\s*([^<]+?)\s*</td>\s*<td[^>]*>\s*(?:<span[^>]*>)?\s*"
            r"\$?([\d,]+\.\d{2}|N/A)",
            m.group(1),
        )
        for label, price_text in rows:
            if label.strip() == FULL_TABLE_PSA10_LABEL:
                return _money(price_text)
    m = re.search(r'id="manual_only_price".{0,300}?' + _MONEY_RE, body, re.S)
    return _money(m.group(1)) if m else None


def parse_psa10_sales_per_month(body: str) -> float | None:
    """Vendas/mês do PSA 10, normalizadas a partir de qualquer período.

    O PriceCharting escreve o volume como "N sales per day|week|month|year" nas
    células da tabela principal, na MESMA ordem das colunas de preço — então a
    do PSA 10 é a de índice PSA10_COLUMN_INDEX. Sem a tabela, ou com menos
    células de volume que isso, devolve None (nunca chuta liquidez).
    """
    m = re.search(r'<table[^>]*id="price_data".*?</table>', body, re.S)
    if not m:
        return None
    volumes = []
    for cell in re.findall(r"<td[^>]*>(.*?)</td>", m.group(0), re.S):
        text = " ".join(html_mod.unescape(re.sub(r"<[^>]+>", " ", cell)).split())
        vm = re.search(r"([\d,]+)\s+sales?\s+per\s+(day|week|month|year)", text)
        if vm:
            n = float(vm.group(1).replace(",", ""))
            per_month = {"day": n * 30, "week": n * 4.33,
                         "month": n, "year": n / 12}[vm.group(2)]
            volumes.append(round(per_month, 1))
    if len(volumes) <= PSA10_COLUMN_INDEX:
        return None
    return volumes[PSA10_COLUMN_INDEX]


def parse_pop_report(body: str) -> dict | None:
    """{'psa': [n1..n10], 'cgc': [n1..n10]} do censo embutido, ou None.

    Listas SEMPRE com 10 posições (nota 1 → índice 0, PSA 10 → índice 9).
    Página sem o objeto (ou malformado) devolve None — nunca zeros inventados.
    """
    m = _POP_DATA_RE.search(body)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return None
    out = {}
    for k in ("psa", "cgc"):
        v = data.get(k)
        if (not isinstance(v, list) or len(v) != 10
                or not all(isinstance(x, int) and x >= 0 for x in v)):
            return None
        out[k] = v
    return out


def parse_tcgplayer_product_id(body: str) -> str | None:
    """productId TCGPlayer da página (chave de join com o catálogo tcgcsv)."""
    m = _TCG_PID_RE.search(body)
    return m.group(1) if m else None


def parse_raw_price(body: str) -> float | None:
    """Preço "Ungraded" (carta crua) da tabela principal — base do prêmio PSA 10."""
    # Na página de produto a célula é `<td id="used_price">`; na tabela de
    # resultados de busca é `class="... used_price"` — aceita os dois.
    m = re.search(r'used_price.{0,300}?' + _MONEY_RE, body, re.S)
    return _money(m.group(1)) if m else None


def pick_search_result(body: str, number: str) -> str | None:
    """URL do produto certo numa página de RESULTADOS de busca, ou None.

    Regra: número da carta no título ("#4") E sem qualificador de variante
    entre colchetes — "[1st Edition]" / "[Shadowless]" são páginas separadas
    no PriceCharting; a página sem qualificador é a impressão comum
    (unlimited), que é a que o operador compra. Primeiro que casar vence
    (a busca já ordena por relevância).
    """
    if not number:
        return None
    num = number.split("/")[0].strip().lstrip("0") or number
    for url, title in _SEARCH_ROW_RE.findall(body):
        clean = " ".join(html_mod.unescape(re.sub(r"<[^>]+>", " ", title)).split())
        if "[" in clean:
            continue
        if re.search(rf"#{re.escape(num)}(?![\w])", clean):
            return url
    return None


def _cache_path(card_name: str, set_name: str, number: str) -> Path:
    key = hashlib.sha1(f"{card_name}|{set_name}|{number}".encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{key}.json"


def _cache_get(card_name: str, set_name: str, number: str) -> dict | None:
    p = _cache_path(card_name, set_name, number)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        age = (date.today() - date.fromisoformat(d["_cached_on"])).days
        if age > CACHE_TTL_DAYS or d.get("status") != "ok":
            return None
        return d
    except (ValueError, KeyError, OSError):
        return None


def _cache_put(card_name: str, set_name: str, number: str, d: dict) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(card_name, set_name, number).write_text(
            json.dumps({**d, "_cached_on": date.today().isoformat()}),
            encoding="utf-8")
    except OSError:
        pass  # cache é conveniência; falha de disco não derruba a consulta


def _extract(body: str, url: str) -> dict:
    """Tudo que o modo graded/low pop lê de UMA página de produto."""
    pop = parse_pop_report(body)
    usd = parse_psa10_price(body)
    return {
        "usd": usd,
        "sales_per_month": parse_psa10_sales_per_month(body),
        "raw_usd": parse_raw_price(body),
        "pop_psa": pop["psa"] if pop else None,
        "pop_cgc": pop["cgc"] if pop else None,
        "tcg_product_id": parse_tcgplayer_product_id(body),
        "url": url,
        "status": "ok" if usd is not None else "sem preço PSA 10",
    }


def _product_matches(url: str, body: str, number: str) -> bool:
    """O número da carta precisa aparecer na URL ou no título (precisão > cobertura)."""
    if not number:
        return False
    num = number.split("/")[0].strip().lstrip("0") or number
    if re.search(rf"[-/]{re.escape(num)}(?:[-/]|$)", url.lower()):
        return True
    title = re.search(r"<title>(.*?)</title>", body, re.S)
    return bool(title and f"#{num}" in title.group(1))


def search_queries(card_name: str, set_name: str, number: str) -> list[str]:
    """Escada de queries do mais específico ao mais frouxo (provada 2026-09-01).

    O que o PriceCharting NÃO aceita, e por isso é normalizado aqui:
      - prefixo de era no set ("SV03: Obsidian Flames" → "Obsidian Flames");
      - qualificador entre parênteses no nome ("Mew V (Alternate Full Art)" →
        "Mew V") — o NÚMERO é o que identifica a variante, e a página do
        produto já é a da variante certa;
      - "#" antes do número (vira %23 e a busca não casa).
    O sufixo "Base Set" cai no 2º degrau: no PriceCharting o set do SV01/SWSH01
    é só "Scarlet & Violet" / "Sword & Shield".
    """
    st = strip_era_prefix(set_name)
    base = re.sub(r"\s*\(.*?\)\s*", " ", card_name).strip() or card_name
    num = _clean_number(number)
    st_sem_base = re.sub(r"\bBase Set\b", "", st, flags=re.I).strip()
    queries, seen = [], set()
    for s in (st, st_sem_base, ""):
        q = " ".join(f"pokemon {s} {base} {num}".split())
        if q not in seen:
            seen.add(q)
            queries.append(q)
    return queries


def fetch_psa10(card_name: str, set_name: str, number: str,
                use_cache: bool = True) -> dict:
    """{'usd', 'sales_per_month', 'raw_usd', 'pop_psa', 'pop_cgc',
        'tcg_product_id', 'url', 'status'} — status é sempre explícito.

    status: 'ok' | 'sem match confiável' | 'sem preço PSA 10' | 'HTTP <code>'
            | 'rede' | 'parse'. Valores None em qualquer status != 'ok'
            (exceto os que a página trouxe mesmo sem preço PSA 10).

    Caminho: query específica → o PriceCharting redireciona direto pro produto;
    query ambígua fica na página de resultados, e aí escolhemos a linha certa
    (`pick_search_result`: número no título, sem variante entre colchetes) e
    abrimos o produto. Em qualquer caso o número da carta tem que casar
    (`_product_matches`) — precisão > cobertura.
    """
    import requests  # local: mantém o módulo importável sem puxar requests

    if use_cache:
        hit = _cache_get(card_name, set_name, number)
        if hit:
            return {k: v for k, v in hit.items() if not k.startswith("_")}

    out = {"usd": None, "sales_per_month": None, "raw_usd": None,
           "pop_psa": None, "pop_cgc": None, "tcg_product_id": None,
           "url": "", "status": ""}
    last_status = "sem match confiável"
    try:
        for query in search_queries(card_name, set_name, number):
            r = requests.get(SEARCH.format(q=quote(query)), headers=HEADERS,
                             timeout=TIMEOUT_S)
            time.sleep(SLEEP_S)  # educado com o site
            if r.status_code != 200:
                last_status = f"HTTP {r.status_code}"
                continue
            url, body = r.url, r.text
            if "/game/" not in url:
                # Página de resultados: escolher a linha certa e abrir.
                pick = pick_search_result(body, number)
                if not pick:
                    continue
                r = requests.get(pick, headers=HEADERS, timeout=TIMEOUT_S)
                time.sleep(SLEEP_S)
                if r.status_code != 200:
                    last_status = f"HTTP {r.status_code}"
                    continue
                url, body = r.url, r.text
            if not _product_matches(url, body, number):
                continue
            out.update(_extract(body, url))
            if use_cache and out["status"] == "ok":
                _cache_put(card_name, set_name, number, out)
            return out
        out["status"] = last_status
        return out
    except requests.RequestException:
        out["status"] = "rede"
        return out
    except Exception:
        out["status"] = "parse"
        return out
