"""Modo low pop (2026-09-21): censo PSA + vendas por nota do PriceCharting como
Escassez e Demanda do score; guards de página fina; eras vintage; entrega."""
from datetime import date

import pytest

from outlook import tcgcsv_api
from outlook.psa10 import (parse_pop_report, parse_raw_price,
                           parse_tcgplayer_product_id, pick_search_result)
from outlook.report import ranking_markdown
from outlook.scoring import (POP_TOTAL_MIN_TRUST, apply_lowpop, demand_points,
                             lowpop_pool, pop_trust_issue, scarcity_points,
                             score_card)

# ── Parsers da página de produto (HTML REAL reduzido, sonda de 2026-09-21) ──

POP_JS = ('<script>VGPC.pop_data = {"cgc":[0,0,0,0,3,0,2,23,95,295],'
          '"psa":[0,0,0,2,6,10,9,102,1095,2595]};</script>')
TCG_LINK = ('<a href="https://partner.tcgplayer.com/c/3029031/1780961/21018?u='
            'https%3A%2F%2Fwww.tcgplayer.com%2Fproduct%2F676088%2F-&amp;sharedId=web">')
RAW_CELL = '<td class="price numeric used_price"><span class="js-price">$914.45</span></td>'


def test_parse_pop_report_le_psa_e_cgc_por_nota():
    pop = parse_pop_report(POP_JS)
    assert pop["psa"][9] == 2595 and pop["psa"][8] == 1095
    assert pop["cgc"][9] == 295
    assert len(pop["psa"]) == len(pop["cgc"]) == 10


@pytest.mark.parametrize("body", [
    "<html>sem censo</html>",
    'VGPC.pop_data = {"psa":[1,2,3]};',                       # 3 notas: malformado
    'VGPC.pop_data = {"psa":[0,0,0,0,0,0,0,0,0,1]};',         # sem cgc
    'VGPC.pop_data = {"psa":"x","cgc":[0,0,0,0,0,0,0,0,0,0]};',
])
def test_parse_pop_report_devolve_none_em_vez_de_inventar(body):
    assert parse_pop_report(body) is None


def test_tcgplayer_id_vem_do_link_de_afiliado_url_encoded():
    assert parse_tcgplayer_product_id(TCG_LINK) == "676088"
    assert parse_tcgplayer_product_id(
        '<a href="https://www.tcgplayer.com/product/42382/-">') == "42382"
    assert parse_tcgplayer_product_id("<html/>") is None


def test_preco_da_carta_crua():
    assert parse_raw_price(RAW_CELL) == 914.45
    assert parse_raw_price("<html/>") is None


SEARCH_HTML = """
<table id="games_table"><tbody>
<tr><td class="title"><a href="https://www.pricecharting.com/game/pokemon-base-set/charizard-1st-edition-4" title="1"> Charizard [1st Edition] #4</a></td></tr>
<tr><td class="title"><a href="https://www.pricecharting.com/game/pokemon-base-set/charizard-shadowless-4" title="2"> Charizard [Shadowless] #4</a></td></tr>
<tr><td class="title"><a href="https://www.pricecharting.com/game/pokemon-base-set/charizard-4" title="3"> Charizard #4</a></td></tr>
<tr><td class="title"><a href="https://www.pricecharting.com/game/pokemon-base-set/charmander-46" title="4"> Charmander #46</a></td></tr>
</tbody></table>"""


def test_resultado_de_busca_escolhe_a_impressao_comum_com_o_numero():
    # 1st Edition / Shadowless são páginas SEPARADAS; a sem colchetes é a unlimited.
    assert (pick_search_result(SEARCH_HTML, "4")
            == "https://www.pricecharting.com/game/pokemon-base-set/charizard-4")


def test_resultado_de_busca_nao_casa_numero_parcial_nem_sem_numero():
    assert pick_search_result(SEARCH_HTML, "46") .endswith("charmander-46")
    assert pick_search_result(SEARCH_HTML, "40") is None
    assert pick_search_result(SEARCH_HTML, "") is None


# ── Faixas e guards ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("pop10,pts", [
    (0, 25), (50, 25), (51, 22), (200, 22), (500, 18), (2000, 12),
    (10000, 7), (10001, 3), (27631, 3),
])
def test_faixas_de_escassez_sao_log(pop10, pts):
    assert scarcity_points(pop10) == pts


@pytest.mark.parametrize("spm,pts", [
    (90.0, 25), (30.0, 25), (29.9, 20), (10.0, 20), (3.0, 14), (1.0, 8),
    (0.9, 3), (0.0, 3),
])
def test_faixas_de_demanda(spm, pts):
    assert demand_points(spm) == pts


def test_guard_censo_fino_e_vendas_impossiveis():
    ok = [0, 0, 0, 2, 6, 10, 9, 102, 1095, 2595]
    assert pop_trust_issue(ok, 90.0) is None
    assert pop_trust_issue(None, 10.0) == "pop n/d"
    # Gardevoir ex 233 (Paldean Fates) na sonda: censo total 2 → página fina.
    fino = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1]
    assert sum(fino) < POP_TOTAL_MIN_TRUST
    assert "página fina" in pop_trust_issue(fino, None)
    # Blastoise 2 na sonda: 4,3 vendas/mês de PSA 10 com só 2 no censo.
    blastoise = [9, 8, 7, 19, 32, 53, 40, 43, 16, 2]
    assert "vendas/mês de PSA 10" in pop_trust_issue(blastoise, 4.3)
    assert pop_trust_issue(blastoise, 1.0) is None


# ── apply_lowpop: troca de régua com fallback declarado ─────────────────────

CARD = {"id": "1", "name": "Charizard ex", "number": "223",
        "rarity": "Special Illustration Rare"}
SET_META = {"id": "s1", "name": "SV03: Obsidian Flames", "series": "Scarlet & Violet",
            "releaseDate": "2023-08-11"}
PAGE = {"usd": 730.0, "sales_per_month": 30.0, "raw_usd": 104.0,
        "pop_psa": [19, 11, 19, 75, 207, 681, 1987, 10966, 27843, 12647],
        "pop_cgc": [0] * 10, "tcg_product_id": "509980", "status": "ok"}


def _carta():
    return score_card(CARD, SET_META, 108.59, today=date(2026, 9, 1))


def test_lowpop_troca_supply_e_preco_por_escassez_e_demanda():
    sc = _carta()
    apply_lowpop(sc, PAGE)
    assert sc.lowpop
    assert sc.pts_scarcity == 3          # 12.647 PSA 10 = nada escasso
    assert sc.pts_demand == 25           # 1 venda/dia
    assert sc.score == (sc.pts_character + sc.pts_rarity
                        + sc.pts_scarcity + sc.pts_demand)
    assert sc.pop_psa10 == 12647 and sc.pop_total == sum(PAGE["pop_psa"])
    assert round(sc.gem_rate, 3) == round(12647 / sum(PAGE["pop_psa"]), 3)
    assert round(sc.psa10_premium, 2) == round(730.0 / 104.0, 2)
    assert sc.tcg_product_id == "509980"
    assert not any("não confiável" in n for n in sc.notes)


def test_lowpop_carta_realmente_escassa_pontua_alto():
    sc = _carta()
    apply_lowpop(sc, {**PAGE, "pop_psa": [0, 0, 0, 0, 1, 2, 4, 20, 60, 45],
                      "sales_per_month": 3.0})
    assert sc.pts_scarcity == 25 and sc.pts_demand == 14


def test_lowpop_censo_nao_confiavel_cai_na_idade_com_nota():
    sc = _carta()
    supply_antes = sc.pts_supply
    apply_lowpop(sc, {**PAGE, "pop_psa": [0, 0, 0, 0, 0, 0, 0, 0, 1, 1]})
    assert sc.pts_scarcity == supply_antes
    assert any("não confiável" in n and "idade do set" in n for n in sc.notes)


def test_lowpop_sem_vendas_cai_no_preco_do_slab_com_nota():
    sc = _carta()
    apply_lowpop(sc, {**PAGE, "sales_per_month": None})
    assert sc.pts_demand == sc.pts_price       # já remedido no slab pelo graded
    assert any("vendas/mês n/d" in n for n in sc.notes)


def test_lowpop_sem_pagina_nenhuma_mantem_reguas_antigas_declaradas():
    sc = _carta()
    apply_lowpop(sc, {"usd": None, "sales_per_month": None, "raw_usd": None,
                      "pop_psa": None, "pop_cgc": None, "tcg_product_id": None,
                      "status": "sem match confiável"})
    assert sc.pts_scarcity == sc.pts_supply and sc.pts_demand == sc.pts_price
    assert sc.score == (sc.pts_character + sc.pts_rarity
                        + sc.pts_supply + sc.pts_price)
    assert sc.pop_psa10 is None and sc.psa10_premium is None


def test_lowpop_premio_baixo_vira_nota():
    sc = _carta()
    apply_lowpop(sc, {**PAGE, "usd": 120.0, "raw_usd": 104.0})
    assert any("prêmio PSA 10 baixo" in n for n in sc.notes)


# ── Entrega ──────────────────────────────────────────────────────────────────

def test_tabela_lowpop_mostra_pop_gem_premio_e_declara_a_regua():
    sc = _carta()
    apply_lowpop(sc, PAGE)
    md = ranking_markdown([sc], 10, lowpop=True)
    assert "Pop PSA10 / total (gem)" in md and "Prêmio" in md
    assert "12,647 / 54,455 (23%)" in md
    assert "7.0×" in md
    assert "Escassez + Demanda" in md and "MODO LOW POP" in md
    assert "[eBay (busca)]" in md and "PriceCharting" in md


def test_tabela_lowpop_separa_censo_nao_confiavel_em_balde_proprio():
    ok = _carta()
    apply_lowpop(ok, PAGE)
    fino = score_card({**CARD, "id": "2", "name": "Gardevoir ex", "number": "233"},
                      SET_META, 172.59, today=date(2026, 9, 1))
    apply_lowpop(fino, {**PAGE, "pop_psa": [0, 0, 0, 0, 0, 0, 0, 0, 1, 1]})
    assert fino.pop_issue and ok.pop_issue is None
    md = ranking_markdown([fino, ok], 10, lowpop=True)
    top, _, bucket = md.partition("### ⚠️ Sem censo confiável")
    assert "Charizard ex" in top and "Gardevoir ex" not in top
    assert "Gardevoir ex" in bucket and "1 / 2 (50%)" in bucket
    assert "Top 1 —" in top


def test_tabela_normal_nao_ganha_colunas_lowpop():
    md = ranking_markdown([_carta()], 10)
    assert "Pop PSA10" not in md and "Supply + Preço" in md


# ── Eras vintage no tcgcsv ───────────────────────────────────────────────────

def test_aliases_de_era():
    assert tcgcsv_api.expand_eras(["vintage"]) == list(tcgcsv_api.VINTAGE_ERAS)
    assert "Scarlet & Violet" in tcgcsv_api.expand_eras(["all"])
    assert tcgcsv_api.expand_eras(["Scarlet & Violet", "vintage", "EX"]) == (
        ["Scarlet & Violet"] + list(tcgcsv_api.VINTAGE_ERAS))


def test_fetch_sets_mapeia_vintage_por_nome_e_ignora_kits(monkeypatch):
    groups = {"results": [
        {"groupId": 604, "name": "Base Set", "publishedOn": "1999-01-09T00:00:00"},
        {"groupId": 1372, "name": "Skyridge", "publishedOn": "2003-05-12T00:00:00"},
        {"groupId": 1393, "name": "EX Ruby and Sapphire", "publishedOn": "2003-06-18T00:00:00"},
        {"groupId": 1543, "name": "EX Trainer Kit 1: Latias & Latios", "publishedOn": "2026-09-20T00:00:00"},
        {"groupId": 1422, "name": "POP Series 1", "publishedOn": "2026-09-20T00:00:00"},
        {"groupId": 2480, "name": "Hidden Fates", "publishedOn": "2019-08-23T00:00:00"},
        {"groupId": 1, "name": "SV03: Obsidian Flames", "publishedOn": "2023-08-11T00:00:00"},
    ]}
    monkeypatch.setattr(tcgcsv_api, "_get_json", lambda url: groups)
    sets = tcgcsv_api.fetch_sets(list(tcgcsv_api.VINTAGE_ERAS), today=date(2026, 9, 21))
    by = {s["name"]: s["series"] for s in sets}
    assert by == {"Base Set": "Wizards of the Coast", "Skyridge": "Wizards of the Coast",
                  "EX Ruby and Sapphire": "EX", "Hidden Fates": "Sun & Moon"}
    # SV continua exigindo a era pedida
    sets_sv = tcgcsv_api.fetch_sets(["Scarlet & Violet"], today=date(2026, 9, 21))
    assert [s["name"] for s in sets_sv] == ["SV03: Obsidian Flames"]


# ── Pool por era ─────────────────────────────────────────────────────────────

def _mk(name, series, rarity, usd, number="1"):
    return score_card({"id": name, "name": name, "number": number, "rarity": rarity},
                      {"id": series, "name": series, "series": series,
                       "releaseDate": "2020-01-01"}, usd, today=date(2026, 9, 1))


def test_pool_lowpop_faz_rodizio_por_era_em_vez_de_top_por_score_cru():
    sv = [_mk(f"Charizard ex {i}", "Scarlet & Violet", "Special Illustration Rare", 100 + i)
          for i in range(6)]
    wotc = [_mk(f"Charizard {i}", "Wizards of the Coast", "Holo Rare", 900 - i)
            for i in range(6)]
    pool = lowpop_pool(sv + wotc, 6)
    assert len(pool) == 6
    assert sum(1 for c in pool if c.series == "Wizards of the Coast") == 3
    assert sum(1 for c in pool if c.series == "Scarlet & Violet") == 3
    # dentro da era, melhor Personagem+Raridade primeiro, depois preço maior
    assert pool[0].market_usd == max(c.market_usd for c in sv) or \
        pool[0].market_usd == max(c.market_usd for c in wotc)


def test_pool_lowpop_era_pequena_cede_vaga():
    sv = [_mk(f"C{i}", "Scarlet & Violet", "Illustration Rare", 50 + i) for i in range(8)]
    ex = [_mk("Rayquaza", "EX", "Holo Rare", 400)]
    pool = lowpop_pool(sv + ex, 6)
    assert len(pool) == 6 and sum(1 for c in pool if c.series == "EX") == 1
