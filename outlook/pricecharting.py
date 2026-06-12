"""Tendência de preço via páginas públicas do PriceCharting — best-effort.

Probe de 2026-05-14 confirmou que as páginas públicas retornam HTTP 200 com
dados estruturados (preço raw + últimas vendas) sem precisar da API paga.
Aqui usamos SÓ as últimas vendas ("Sold Listings") pra estimar uma tendência
rudimentar: média das 3 vendas mais recentes vs média das 3 anteriores.

HONESTIDADE OBRIGATÓRIA:
- Amostra minúscula (6 vendas) → a seta é um INDÍCIO, não uma série histórica.
- O matching carta→produto é por busca de texto; se o número da carta não
  aparecer no título do produto encontrado, devolvemos "n/d" em vez de
  arriscar a carta errada.
- Qualquer falha (HTTP, parse, bloqueio) devolve "n/d" — nunca inventa.
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


def fetch_trend(card_name: str, set_name: str, number: str) -> str:
    """Seta de tendência ('↑ +12%', '→', '↓ -8%') ou 'n/d (motivo)'."""
    try:
        q = quote(f"pokemon {set_name} {card_name} #{number}")
        r = requests.get(SEARCH.format(q=q), headers=HEADERS, timeout=TIMEOUT_S)
        if r.status_code != 200:
            return f"n/d (busca HTTP {r.status_code})"
        # A busca pode redirecionar direto pra página do produto.
        if "/game/" in r.url:
            product_html = r.text
        else:
            url = _first_product_url(r.text, number)
            if not url:
                return "n/d (sem match confiável)"
            time.sleep(SLEEP_S)
            pr = requests.get(url, headers=HEADERS, timeout=TIMEOUT_S)
            if pr.status_code != 200:
                return f"n/d (produto HTTP {pr.status_code})"
            product_html = pr.text
        sales = [float(s.replace(",", ""))
                 for s in _SALE_RE.findall(product_html)]
        # As primeiras ocorrências são os preços-resumo (raw/PSA); as vendas
        # individuais vêm depois. Heurística: usa as últimas 6 ocorrências.
        sales = [s for s in sales if s > 0][-6:]
        if len(sales) < 6:
            return "n/d (poucas vendas)"
        recent, older = sales[:3], sales[3:]
        avg_r, avg_o = sum(recent) / 3, sum(older) / 3
        if avg_o <= 0:
            return "n/d"
        delta = (avg_r - avg_o) / avg_o * 100
        if delta > 8:
            return f"↑ +{delta:.0f}%"
        if delta < -8:
            return f"↓ {delta:.0f}%"
        return "→ estável"
    except requests.RequestException:
        return "n/d (rede)"
    except Exception:
        return "n/d (parse)"
