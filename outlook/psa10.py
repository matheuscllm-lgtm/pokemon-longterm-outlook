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
from urllib.parse import quote, unquote, urlparse

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
    """Valor em US$, ou None. "$0.00" é None: o PriceCharting escreve zero
    quando NÃO há venda naquela nota — ausência de dado, não preço (run de
    2026-09-21: 5 linhas saíram com "PSA 10 US$ 0.00" e prêmio 0.0×)."""
    try:
        v = float(text.replace(",", "").replace("$", ""))
    except (ValueError, AttributeError):
        return None
    return v if v > 0 else None


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


# ── Guard de SET ─────────────────────────────────────────────────────────────
# O número sozinho NÃO identifica a carta: no run canônico de 2026-09-21, 20 das
# 278 consultas "ok" aceitaram a página de OUTRO set com o mesmo número (Zapdos
# ex #116 de FireRed & LeafGreen levou preço/censo do Mega Greninja ex #116 de
# Chaos Rising). Set + número identifica. O set da página vem do slug da URL
# (/game/<set>/<carta>); o do catálogo vem do tcgcsv, que enfeita o nome com
# marcador de era e de subset — esses tokens não existem no PriceCharting.
_SET_NOISE = {"pokemon", "and", "the", "of", "vs",
              "xy", "sm", "ex",                      # marcador de era
              "base", "set",                         # "SV01: … Base Set"
              "shiny", "vault", "trainer", "gallery", "galarian"}  # subsets
# Variante de IMPRESSÃO no slug da carta ("charizard-1st-edition-4",
# "gengar-reverse-holo-27"): página separada, outro censo, outro preço. Só
# vale quando o próprio set do catálogo pede a variante ("Base Set (Shadowless)").
_PRINT_VARIANTS = {"1st", "edition", "shadowless", "reverse"}


def _tokens(text: str) -> set[str]:
    return set(_token_list(text))


def _token_list(text: str) -> list[str]:
    text = unquote(html_mod.unescape(text)).lower().replace("'", "").replace("’", "")
    return [t for t in re.split(r"[^a-z0-9]+", text) if t]


def _set_matches(url: str, set_name: str) -> bool:
    """A página é do MESMO set do catálogo? (comparação por tokens do slug)

    Igualdade, não subconjunto: "scarlet-&-violet" é subconjunto de "Scarlet &
    Violet 151" e é OUTRO set, com números que colidem. O PriceCharting hifeniza
    dentro da palavra ("fire-red-&-leaf-green" ↔ "FireRed & LeafGreen"), então
    a igualdade também vale pra sequência de tokens colada. Qualificador entre
    parênteses no set ("Base Set (Shadowless)") é variante de impressão e tem
    que aparecer no slug do set ou da carta — sem ele a página é a unlimited;
    e variante no slug da carta que o catálogo NÃO pediu reprova.
    """
    parts = urlparse(url).path.split("/")
    if len(parts) < 4 or parts[1] != "game":
        return False
    set_list, card_list = _token_list(parts[2]), _token_list(parts[3])
    slug_set, slug_card = set(set_list), set(card_list)
    qualifier = _tokens(" ".join(re.findall(r"\((.*?)\)", set_name)))
    cat_list = _token_list(re.sub(r"\(.*?\)", " ", strip_era_prefix(set_name)))
    noise = _SET_NOISE
    if not (set(cat_list) - noise) or not (slug_set - noise):
        noise = {"pokemon"}                 # "Base Set": o nome É o ruído
    core_cat = [t for t in cat_list if t not in noise]
    core_slug = [t for t in set_list if t not in noise]
    if not core_cat:
        return False
    if set(core_cat) != set(core_slug) and "".join(core_cat) != "".join(core_slug):
        return False
    if _unwanted_print_variant(url, set_name):
        return False
    return qualifier <= (slug_set | slug_card)


def _unwanted_print_variant(url: str, set_name: str) -> bool:
    """Slug da carta traz variante de impressão que o set do catálogo não pediu."""
    parts = urlparse(url).path.split("/")
    if len(parts) < 4:
        return False
    qualifier = _tokens(" ".join(re.findall(r"\((.*?)\)", set_name)))
    return bool((_tokens(parts[3]) & _PRINT_VARIANTS) - qualifier)


def pick_search_result(body: str, number: str, set_name: str = "") -> str | None:
    """URL do produto certo numa página de RESULTADOS de busca, ou None.

    Regra: número da carta no título ("#4"), página do mesmo set (quando o set
    é informado — ver `_set_matches`) E sem qualificador de variante entre
    colchetes — "[1st Edition]" / "[Shadowless]" são páginas separadas no
    PriceCharting; a página sem qualificador é a impressão comum (unlimited),
    que é a que o operador compra. Exceção: quando o PRÓPRIO set do catálogo é
    a variante ("Base Set (Shadowless)"), a linha certa é a que traz exatamente
    esse qualificador. Primeiro que casar vence (a busca ordena por relevância).
    """
    if not number:
        return None
    num = number.split("/")[0].strip().lstrip("0") or number
    qualifier = _tokens(" ".join(re.findall(r"\((.*?)\)", set_name)))
    for url, title in _SEARCH_ROW_RE.findall(body):
        clean = " ".join(html_mod.unescape(re.sub(r"<[^>]+>", " ", title)).split())
        if _tokens(" ".join(re.findall(r"\[(.*?)\]", clean))) != qualifier:
            continue
        if set_name and not _set_matches(url, set_name):
            continue
        if re.search(rf"#{re.escape(num)}(?![\w])", clean):
            # O href vem HTML-escapado ("…-&amp;-…"); aberto cru, o site não
            # acha a página e o set inteiro vira "sem match" (151, DP, FRLG…).
            return html_mod.unescape(url)
    return None


def _cache_path(card_name: str, set_name: str, number: str) -> Path:
    key = hashlib.sha1(f"{card_name}|{set_name}|{number}".encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{key}.json"


def _cache_get(card_name: str, set_name: str, number: str,
               tcg_product_id: str | None = None) -> dict | None:
    p = _cache_path(card_name, set_name, number)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        age = (date.today() - date.fromisoformat(d["_cached_on"])).days
        if age > CACHE_TTL_DAYS or d.get("status") != "ok":
            return None
        # O cache guarda o que o guard DA ÉPOCA aceitou. Revalida com o guard
        # de hoje: página de outro set ou preço zerado vira miss e é refeita.
        # Sem o HTML, o número só é conferido pela URL — entrada cujo número
        # casou apenas pelo <title> vira miss e é refeita (0 casos nas 253
        # entradas boas do run de 2026-09-21; custo é rede, nunca dado errado).
        if not d.get("usd") or not _product_matches(
                d.get("url", ""), "", number, set_name,
                tcg_product_id, d.get("tcg_product_id")):
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


def _number_matches(url: str, body: str, number: str) -> bool:
    if not number:
        return False
    num = number.split("/")[0].strip().lstrip("0") or number
    if re.search(rf"[-/]{re.escape(num.lower())}(?:[-/]|$)",
                 urlparse(url).path.lower()):
        return True
    # Título: número EXATO ("#4" não pode casar "#46") — mesma regra do
    # pick_search_result; sem isso um redirect pra carta errada seria aceito e
    # ficaria no cache como "ok" (achado da revisão de 2026-09-21).
    title = re.search(r"<title>(.*?)</title>", body, re.S)
    return bool(title and re.search(rf"#{re.escape(num)}(?![\w])",
                                    title.group(1), re.I))


def _product_matches(url: str, body: str, number: str, set_name: str = "",
                     tcg_product_id: str | None = None,
                     page_product_id: str | None = None) -> bool:
    """A página é a da carta? Número E set têm que bater (precisão > cobertura).

    O set é provado de um de dois jeitos: a página declara o MESMO productId
    TCGPlayer do catálogo (identidade direta — cobre sets que o PriceCharting
    chama por outro nome, "SM Base Set" → "sun-&-moon"), ou o slug do set casa
    com o nome do catálogo (`_set_matches`). productId DIFERENTE não reprova
    sozinho: o PriceCharting às vezes aponta pra impressão irmã da mesma carta.
    Pelo mesmo motivo, productId IGUAL não resgata variante de impressão no
    slug ("charizard-1st-edition-4" com link pro produto unlimited): é outra
    página, outro censo. Sem `set_name` (chamada antiga) vale só o número.
    """
    if not _number_matches(url, body, number):
        return False
    if set_name and _unwanted_print_variant(url, set_name):
        return False
    if tcg_product_id and page_product_id and str(tcg_product_id) == str(page_product_id):
        return True
    return _set_matches(url, set_name) if set_name else True


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
                use_cache: bool = True,
                tcg_product_id: str | None = None) -> dict:
    """{'usd', 'sales_per_month', 'raw_usd', 'pop_psa', 'pop_cgc',
        'tcg_product_id', 'url', 'status'} — status é sempre explícito.

    status: 'ok' | 'sem match confiável' | 'sem preço PSA 10' | 'HTTP <code>'
            | 'rede' | 'parse'. Valores None em qualquer status != 'ok'
            (exceto os que a página trouxe mesmo sem preço PSA 10).

    Caminho: query específica → o PriceCharting redireciona direto pro produto;
    query ambígua fica na página de resultados, e aí escolhemos a linha certa
    (`pick_search_result`: número no título, sem variante entre colchetes) e
    abrimos o produto. Em qualquer caso o número E o set da carta têm que casar
    (`_product_matches`) — precisão > cobertura. `tcg_product_id` é o productId
    TCGPlayer do catálogo (o card_id da fonte tcgcsv); quando a página declara
    o mesmo id, a identidade está provada mesmo com nome de set divergente.
    """
    import requests  # local: mantém o módulo importável sem puxar requests

    if use_cache:
        hit = _cache_get(card_name, set_name, number, tcg_product_id)
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
                pick = pick_search_result(body, number, set_name)
                if not pick:
                    continue
                r = requests.get(pick, headers=HEADERS, timeout=TIMEOUT_S)
                time.sleep(SLEEP_S)
                if r.status_code != 200:
                    last_status = f"HTTP {r.status_code}"
                    continue
                url, body = r.url, r.text
            if not _product_matches(url, body, number, set_name, tcg_product_id,
                                    parse_tcgplayer_product_id(body)):
                last_status = "sem match confiável"  # página veio, carta não bate
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
