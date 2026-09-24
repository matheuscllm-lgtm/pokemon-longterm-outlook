"""Cobertura do match carta→página (handoff 2026-09-23, itens 2.1/2.2).

Três buracos reais do run canônico de 2026-09-22, provados por sonda ao vivo:

1. Numeração "H" dos e-Card (Aquapolis/Skyridge): o catálogo escreve `H09`,
   o PriceCharting escreve `#H9` (sem zero depois da letra). A linha certa
   ESTAVA na página de resultados; o matcher é que procurava `#H09`.
2. Página fina/duplicada: pra holo rare de era DP/HGSS/BW o PriceCharting tem
   DUAS páginas com o mesmo set+número — a comum ("Gardevoir #8", productId
   125076 = versão não-holo de theme deck, sem preço e sem censo) e a
   "[Holo]" (productId 85636 = o card_id do catálogo, com preço e censo).
   A regra "sem colchetes" escolhia a fina. A irmã só entra quando o
   productId PROVA a identidade (Lucario #14 CoL: nenhuma das páginas
   declara o card_id 86881 → continua n/d, honesto).
3. Set com <6 meses: censo mensal ainda não incorporou (`pop 0/0`); a nota
   dizia "página fina/duplicada" — enganosa.
"""
from datetime import date

import pytest
import requests

from outlook import psa10
from outlook.psa10 import (_number_matches, _product_matches, fetch_psa10,
                           pick_search_result)
from outlook.scoring import apply_lowpop, pop_trust_issue, score_card

PC = "https://www.pricecharting.com/game/"


def _row(url, title):
    return f'<tr><td class="title"><a href="{url}" title="x"> {title}</a></td></tr>'


def _table(*rows):
    return '<table id="games_table"><tbody>' + "".join(rows) + "</tbody></table>"


# ── 1. Numeração H dos e-Card ────────────────────────────────────────────────

# Linhas REAIS da busca "pokemon Aquapolis Espeon H09" (sonda 2026-09-23).
SEARCH_AQUAPOLIS = _table(
    _row(PC + "pokemon-aquapolis/lugia-149", "Lugia #149"),
    _row(PC + "pokemon-evolving-skies/espeon-v-180", "Espeon V #180"),
    _row(PC + "pokemon-aquapolis/umbreon-h29", "Umbreon #H29"),
    _row(PC + "pokemon-aquapolis/espeon-h9", "Espeon #H9"),
)


@pytest.mark.parametrize("number,slug", [
    ("H09", "espeon-h9"), ("H9", "espeon-h9"), ("H09/147", "espeon-h9"),
])
def test_numero_h_do_ecard_casa_sem_o_zero_depois_da_letra(number, slug):
    assert (pick_search_result(SEARCH_AQUAPOLIS, number, "Aquapolis")
            == PC + f"pokemon-aquapolis/{slug}")
    assert _product_matches(PC + f"pokemon-aquapolis/{slug}",
                            "<title>Espeon #H9 Prices | Pokemon Aquapolis</title>",
                            number, "Aquapolis")


def test_numero_h_continua_exato():
    # H09 não pode virar H29/H90 nem casar número sem a letra.
    assert not _number_matches(PC + "pokemon-aquapolis/umbreon-h29",
                               "<title>Umbreon #H29</title>", "H09")
    assert not _number_matches(PC + "pokemon-aquapolis/x-h90",
                               "<title>X #H90</title>", "H09")
    assert not _number_matches(PC + "pokemon-aquapolis/x-9",
                               "<title>X #9</title>", "H09")
    assert pick_search_result(SEARCH_AQUAPOLIS, "H29", "Aquapolis").endswith("umbreon-h29")
    assert pick_search_result(SEARCH_AQUAPOLIS, "9", "Aquapolis") is None


def test_numero_com_letra_sem_zero_nao_muda():
    # TG16, 25 (de 025): comportamento anterior preservado.
    assert _number_matches(PC + "pokemon-brilliant-stars/x-tg16", "", "TG16")
    assert _number_matches(PC + "pokemon-base-set/x-25", "", "025")
    assert not _number_matches(PC + "pokemon-base-set/x-250", "", "025")


# ── 2. Página fina → irmã [Holo] só com productId ────────────────────────────

def _page(title, pid, psa10_usd=None, pop=None):
    body = f"<title>{title} Prices | Pokemon</title>"
    if pid:
        body += f'<a href="https://www.tcgplayer.com/product/{pid}/-">tcg</a>'
    if pop is not None:
        body += ('<script>VGPC.pop_data = {"cgc":[0,0,0,0,0,0,0,0,0,0],'
                 f'"psa":{pop}}};</script>')
    if psa10_usd is not None:
        body += ('<div id="full-prices"><table><tr><td>PSA 10</td>'
                 f'<td>${psa10_usd:,.2f}</td></tr></table></div>')
    return body


# Sonda 2026-09-23 (Platinum Gardevoir #8): comum = fina, [Holo] = a carta.
PAGES_GARDEVOIR = {
    PC + "pokemon-platinum/gardevoir-8":
        _page("Gardevoir #8", "125076", None, [0] * 10),
    PC + "pokemon-platinum/gardevoir-holo-8":
        _page("Gardevoir [Holo] #8", "85636", 3612.57,
              [0, 0, 0, 0, 1, 2, 10, 38, 100, 8]),
}
SEARCH_GARDEVOIR = _table(
    _row(PC + "pokemon-platinum/gardevoir-8", "Gardevoir #8"),
    _row(PC + "pokemon-platinum/gardevoir-holo-8", "Gardevoir [Holo] #8"),
    _row(PC + "pokemon-platinum/gardevoir-reverse-holo-8", "Gardevoir [Reverse Holo] #8"),
)
# Sonda 2026-09-23 (Call of Legends Lucario #14): nenhuma página declara o
# card_id 86881 do catálogo → a irmã NÃO prova identidade.
PAGES_LUCARIO = {
    PC + "pokemon-call-of-legends/lucario-14":
        _page("Lucario #14", "91655", None, [0] * 10),
    PC + "pokemon-call-of-legends/lucario-holo-14":
        _page("Lucario [Holo] #14", "125059", 5985.70,
              [0, 0, 0, 0, 0, 1, 5, 20, 32, 1]),
    PC + "pokemon-call-of-legends/lucario-reverse-holo-14":
        _page("Lucario [Reverse Holo] #14", "86881", 999.0,
              [0, 0, 0, 0, 0, 1, 5, 20, 32, 1]),
}
SEARCH_LUCARIO = _table(
    _row(PC + "pokemon-call-of-legends/lucario-holo-14", "Lucario [Holo] #14"),
    _row(PC + "pokemon-call-of-legends/lucario-14", "Lucario #14"),
    _row(PC + "pokemon-call-of-legends/lucario-reverse-holo-14", "Lucario [Reverse Holo] #14"),
)


class _Resp:
    def __init__(self, url, text):
        self.url, self.text, self.status_code = url, text, 200


def _fake_site(monkeypatch, search_body, pages):
    opened = []

    def get(url, **kw):
        opened.append(url)
        if "search-products" in url:
            return _Resp(url, search_body)
        return _Resp(url, pages[url])
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(psa10.time, "sleep", lambda s: None)
    return opened


def test_pagina_fina_sem_preco_e_sem_censo_tenta_a_irma_holo_com_product_id(monkeypatch):
    opened = _fake_site(monkeypatch, SEARCH_GARDEVOIR, PAGES_GARDEVOIR)
    r = fetch_psa10("Gardevoir", "Platinum", "8", use_cache=False,
                    tcg_product_id="85636")
    assert r["status"] == "ok" and r["usd"] == 3612.57
    assert r["url"].endswith("gardevoir-holo-8") and r["tcg_product_id"] == "85636"
    assert r["pop_psa"][9] == 8
    # A comum foi aberta primeiro (regra vigente); a reverse nunca.
    assert opened[1].endswith("gardevoir-8")
    assert not any("reverse" in u for u in opened)


def test_irma_sem_product_id_igual_nao_entra(monkeypatch):
    opened = _fake_site(monkeypatch, SEARCH_LUCARIO, PAGES_LUCARIO)
    r = fetch_psa10("Lucario", "Call of Legends", "14", use_cache=False,
                    tcg_product_id="86881")
    # Fica com a página comum (fina) — n/d honesto, nunca o preço da [Holo]
    # (productId 125059 ≠ 86881) nem o da [Reverse Holo] (variante de impressão
    # que o catálogo não pediu, mesmo com o productId batendo).
    assert r["status"] == "sem preço PSA 10" and r["usd"] is None
    assert r["url"].endswith("lucario-14")
    assert not any("reverse" in u for u in opened)


def test_sem_product_id_do_catalogo_a_irma_nunca_entra(monkeypatch):
    _fake_site(monkeypatch, SEARCH_GARDEVOIR, PAGES_GARDEVOIR)
    r = fetch_psa10("Gardevoir", "Platinum", "8", use_cache=False)
    assert r["status"] == "sem preço PSA 10" and r["url"].endswith("gardevoir-8")


def test_pagina_comum_com_preco_nao_e_trocada_pela_irma(monkeypatch):
    pages = {**PAGES_GARDEVOIR,
             PC + "pokemon-platinum/gardevoir-8":
                 _page("Gardevoir #8", "125076", 50.0, [0] * 9 + [3])}
    opened = _fake_site(monkeypatch, SEARCH_GARDEVOIR, pages)
    r = fetch_psa10("Gardevoir", "Platinum", "8", use_cache=False,
                    tcg_product_id="85636")
    assert r["url"].endswith("gardevoir-8") and r["usd"] == 50.0
    assert len(opened) == 2


def test_irma_aceita_e_revalidada_pelo_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(psa10, "CACHE_DIR", tmp_path)
    _fake_site(monkeypatch, SEARCH_GARDEVOIR, PAGES_GARDEVOIR)
    r = fetch_psa10("Gardevoir", "Platinum", "8", tcg_product_id="85636")
    assert r["status"] == "ok"
    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("rede"))
    again = fetch_psa10("Gardevoir", "Platinum", "8", tcg_product_id="85636")
    assert again["url"].endswith("gardevoir-holo-8") and again["usd"] == 3612.57


def test_irma_no_cache_nao_e_servida_sem_o_mesmo_product_id(tmp_path, monkeypatch):
    # Achado da revisão: a irmã só entrou no cache porque o productId provou a
    # identidade; uma chamada sem id (--source ptcg) ou com outro id não pode
    # herdar essa prova — refaz a consulta e fica com a comum (fina), n/d.
    monkeypatch.setattr(psa10, "CACHE_DIR", tmp_path)
    _fake_site(monkeypatch, SEARCH_GARDEVOIR, PAGES_GARDEVOIR)
    assert fetch_psa10("Gardevoir", "Platinum", "8", tcg_product_id="85636")["status"] == "ok"
    for pid in (None, "125076"):
        r = fetch_psa10("Gardevoir", "Platinum", "8", tcg_product_id=pid)
        assert r["status"] == "sem preço PSA 10" and r["url"].endswith("gardevoir-8")
    # Entrada comum (não irmã) segue valendo sem id, como antes.
    pages = {**PAGES_GARDEVOIR,
             PC + "pokemon-platinum/gardevoir-8":
                 _page("Gardevoir #8", "125076", 50.0, [0] * 9 + [3])}
    _fake_site(monkeypatch, SEARCH_GARDEVOIR, pages)
    assert fetch_psa10("Gardevoir", "Platinum", "8", tcg_product_id="125076")["usd"] == 50.0
    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("rede"))
    assert fetch_psa10("Gardevoir", "Platinum", "8")["usd"] == 50.0


# ── 3. Set novo: censo ainda não publicado ───────────────────────────────────

def test_set_com_menos_de_6_meses_sem_censo_ganha_nota_especifica():
    assert "censo ainda não publicado" in pop_trust_issue([0] * 10, None, age_months=2)
    assert "censo ainda não publicado" in pop_trust_issue(None, None, age_months=5)
    assert "página fina" in pop_trust_issue([0] * 10, None, age_months=6)
    assert pop_trust_issue(None, None, age_months=12) == "pop n/d"
    assert pop_trust_issue(None, None) == "pop n/d"                # sem idade
    # Censo publicado e fino em set novo continua "página fina".
    assert "página fina" in pop_trust_issue([0] * 9 + [3], None, age_months=2)


def test_lowpop_set_novo_declara_censo_nao_publicado():
    card = {"id": "717605", "name": "Mew ex", "number": "152",
            "rarity": "Special Illustration Rare"}
    meta = {"id": "24722", "name": "ME: 30th Celebration", "series": "Mega Evolution",
            "releaseDate": "2026-08-15"}
    page = {"usd": None, "sales_per_month": None, "raw_usd": None,
            "pop_psa": None, "pop_cgc": None, "tcg_product_id": "717605",
            "url": PC + "pokemon-30th-celebration/mew-ex-152",
            "status": "sem preço PSA 10"}
    sc = score_card(card, meta, 250.0, today=date(2026, 9, 22))
    apply_lowpop(sc, page, today=date(2026, 9, 22))          # 1 mês
    assert sc.pts_scarcity == sc.pts_supply
    assert any("censo ainda não publicado" in n for n in sc.notes)
    assert not any("página fina" in n for n in sc.notes)
    # Mesmo set, 1 ano depois: censo ausente já não tem desculpa de idade.
    sc = score_card(card, meta, 250.0, today=date(2027, 9, 22))
    apply_lowpop(sc, page, today=date(2027, 9, 22))
    assert any("pop n/d" in n for n in sc.notes)
