"""Tendência de preço via páginas públicas do PriceCharting — best-effort.

⚠️ DESATUALIZADO (probe 2026-06-20): o PriceCharting passou a renderizar as
vendas concluídas via JS/AJAX — o HTML público não traz mais a tabela de "Sold
Listings", então este scrape devolve "n/d" na prática. Mantido por
compatibilidade do `--trend`, mas SEM garantia de dados. Para tendência
realizada CONFIÁVEL use a calibração (run_evaluate.py / outlook.evaluate), que
lê avg7/avg30 do CardMarket direto da pokemontcg.io — robusto, sem scraping.

Quando funcionava: usava só as últimas vendas ("Sold Listings"), média das 3
mais recentes vs as 3 anteriores. A lógica abaixo segue intacta caso o HTML
público volte a expor as vendas.

HONESTIDADE OBRIGATÓRIA:
- Amostra minúscula (6 vendas) → a seta seria um INDÍCIO, não série histórica.
- Matching carta→produto por texto; sem match confiável → "n/d".
- Qualquer falha (HTTP, parse, bloqueio, ausência de dados) → "n/d", nunca inventa.
"""
from __future__ import annotations

import re
import time
from urllib.parse import quote

import requests

SEARCH = "https://www.pricecharting.com/search-products?type=prices&q={q}"
HEADERS = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/126.0 Safari/537.36")}
TIMEOUT_S = 20
SLEEP_S = 1.5  # educado com o site; só rodamos no top-N mesmo

_SALE_RE = re.compile(r'class="js-price[^"]*"[^>]*>\s*\$([0-9,]+\.?\d*)')


def _first_product_url(html: str, number: str) -> str | None:
    """Primeiro link de produto cujo contexto contém o número da carta."""
    for m in re.finditer(r'href="(/game/[^"]+)"[^>]*>([^<]*)', html):
        url, text = m.group(1), m.group(2)
        if number and (f"#{number}" in text or f"#{number}" in url):
            return "https://www.pricecharting.com" + url
    return None


def _fetch_sales(card_name: str, set_name: str,
                 number: str) -> tuple[list[float] | None, str]:
    """Últimas ~6 vendas do produto, ou (None, motivo). Nunca inventa.

    Isola a parte de rede/parse — reutilizada por fetch_trend (seta p/ humano)
    e trend_pct (número p/ o avaliador de calibração).
    """
    try:
        q = quote(f"pokemon {set_name} {card_name} #{number}")
        r = requests.get(SEARCH.format(q=q), headers=HEADERS, timeout=TIMEOUT_S)
        if r.status_code != 200:
            return None, f"busca HTTP {r.status_code}"
        # A busca pode redirecionar direto pra página do produto.
        if "/game/" in r.url:
            product_html = r.text
        else:
            url = _first_product_url(r.text, number)
            if not url:
                return None, "sem match confiável"
            time.sleep(SLEEP_S)
            pr = requests.get(url, headers=HEADERS, timeout=TIMEOUT_S)
            if pr.status_code != 200:
                return None, f"produto HTTP {pr.status_code}"
            product_html = pr.text
        sales = [float(s.replace(",", ""))
                 for s in _SALE_RE.findall(product_html)]
        # As primeiras ocorrências são os preços-resumo (raw/PSA); as vendas
        # individuais vêm depois. Heurística: usa as últimas 6 ocorrências.
        sales = [s for s in sales if s > 0][-6:]
        if len(sales) < 6:
            return None, "poucas vendas"
        return sales, ""
    except requests.RequestException:
        return None, "rede"
    except Exception:
        return None, "parse"


def _delta_pct(sales: list[float]) -> float | None:
    """Variação % das 3 vendas recentes vs as 3 anteriores (ou None)."""
    recent, older = sales[:3], sales[3:]
    avg_r, avg_o = sum(recent) / 3, sum(older) / 3
    if avg_o <= 0:
        return None
    return (avg_r - avg_o) / avg_o * 100


def trend_pct(card_name: str, set_name: str, number: str) -> float | None:
    """Variação % realizada (numérica) p/ o avaliador de calibração, ou None.

    Mesma amostra/limitação do fetch_trend — 6 vendas públicas, indício apenas.
    """
    sales, _ = _fetch_sales(card_name, set_name, number)
    return _delta_pct(sales) if sales else None


def fetch_trend(card_name: str, set_name: str, number: str) -> str:
    """Seta de tendência ('↑ +12%', '→ estável', '↓ -8%') ou 'n/d (motivo)'."""
    sales, reason = _fetch_sales(card_name, set_name, number)
    if not sales:
        return f"n/d ({reason})"
    delta = _delta_pct(sales)
    if delta is None:
        return "n/d"
    if delta > 8:
        return f"↑ +{delta:.0f}%"
    if delta < -8:
        return f"↓ {delta:.0f}%"
    return "→ estável"
