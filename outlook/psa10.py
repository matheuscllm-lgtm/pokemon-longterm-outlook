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

import html as html_mod
import re
import time
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


def fetch_psa10(card_name: str, set_name: str, number: str) -> dict:
    """{'usd', 'sales_per_month', 'url', 'status'} — status é sempre explícito.

    status: 'ok' | 'sem match confiável' | 'sem preço PSA 10' | 'HTTP <code>'
            | 'rede' | 'parse'. Valor None em qualquer status != 'ok'.
    """
    import requests  # local: mantém o módulo importável sem puxar requests

    out = {"usd": None, "sales_per_month": None, "url": "", "status": ""}
    last_status = "sem match confiável"
    try:
        for query in search_queries(card_name, set_name, number):
            r = requests.get(SEARCH.format(q=quote(query)), headers=HEADERS,
                             timeout=TIMEOUT_S)
            time.sleep(SLEEP_S)  # educado com o site; só rodamos no top-N
            if r.status_code != 200:
                last_status = f"HTTP {r.status_code}"
                continue
            # Busca específica redireciona direto pro produto; requests segue o
            # redirect e expõe a URL final em r.url (é o que identifica a
            # página). Busca ambígua fica na /search-products e não serve.
            if "/game/" not in r.url or not _product_matches(r.url, r.text, number):
                last_status = "sem match confiável"
                continue
            out["url"] = r.url
            out["usd"] = parse_psa10_price(r.text)
            out["sales_per_month"] = parse_psa10_sales_per_month(r.text)
            out["status"] = "ok" if out["usd"] is not None else "sem preço PSA 10"
            return out
        out["status"] = last_status
        return out
    except requests.RequestException:
        out["status"] = "rede"
        return out
    except Exception:
        out["status"] = "parse"
        return out
