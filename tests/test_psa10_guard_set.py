"""Guard de SET no match carta→página do PriceCharting (achado do run 2026-09-21).

O guard antigo conferia só o NÚMERO da carta. No run canônico low pop, 20 das
278 consultas com status ok aceitaram a página de OUTRO set com o mesmo número
(Zapdos ex #116 de FireRed & LeafGreen recebeu preço/censo do Mega Greninja ex
#116 de Chaos Rising). Verdade de campo usada na auditoria: o productId
TCGPlayer que a própria página declara × o card_id do catálogo tcgcsv.

Os pares (set do catálogo × slug de set do PriceCharting) abaixo são REAIS,
tirados do cache daquele run; nas páginas certas o slug da carta é ilustrativo
("x-<número>") quando a identidade da carta não importa pro teste.
"""
import json
from datetime import date

import pytest

from outlook import psa10
from outlook.psa10 import (_product_matches, parse_psa10_price,
                           parse_raw_price, pick_search_result)

PC = "https://www.pricecharting.com/game/"

# (set do catálogo, número, URL aceita pelo guard antigo) — página ERRADA.
PAGINA_DE_OUTRO_SET = [
    ("EX FireRed & LeafGreen", "116", PC + "pokemon-chaos-rising/mega-greninja-ex-116"),
    ("EX FireRed & LeafGreen", "109", PC + "pokemon-phantasmal-flames/mega-charizard-x-ex-109"),
    ("EX FireRed & LeafGreen", "114", PC + "pokemon-japanese-abyss-eye/mega-darkrai-ex-114"),
    ("XY - Flashfire", "13", PC + "pokemon-phantasmal-flames/mega-charizard-x-ex-13"),
    ("XY - Furious Fists", "113", PC + "pokemon-ascended-heroes/mega-lucario-ex-113"),
    ("EX Deoxys", "8", PC + "pokemon-celebrations/dark-gyarados-8"),
    ("SM - Team Up", "182",
     PC + "pokemon-scarlet-&-violet-151/venusaur-ex-182?q=venusaur+ex+182"),
    ("SM - Ultra Prism", "159", PC + "pokemon-lost-thunder/lugia-gx-159"),
    ("XY - BREAKthrough", "63",
     PC + "pokemon-japanese-mega-dream-ex/team-rocket%27s-mewtwo-ex-63"),
]

# (set do catálogo, número, URL) — página CERTA (productId conferiu no run).
PAGINA_DO_SET_CERTO = [
    ("SWSH07: Evolving Skies", "205", PC + "pokemon-evolving-skies/leafeon-vmax-205"),
    ("Hidden Fates: Shiny Vault", "SV76", PC + "pokemon-hidden-fates/sylveon-gx-sv76"),
    ("SM - Cosmic Eclipse", "240", PC + "pokemon-cosmic-eclipse/x-240"),
    ("XY - Evolutions", "102", PC + "pokemon-evolutions/m-blastoise-ex-102"),
    ("SV01: Scarlet & Violet Base Set", "1", PC + "pokemon-scarlet-&-violet/x-1"),
    ("SWSH: Crown Zenith: Galarian Gallery", "GG44", PC + "pokemon-crown-zenith/x-gg44"),
    ("SWSH11: Lost Origin Trainer Gallery", "TG01", PC + "pokemon-lost-origin/x-tg01"),
    ("SV: Scarlet & Violet 151", "200",
     PC + "pokemon-scarlet-&-violet-151/blastoise-ex-200"),
    ("Call of Legends", "14", PC + "pokemon-call-of-legends/lucario-14"),
]


@pytest.mark.parametrize("set_name,number,url", PAGINA_DE_OUTRO_SET)
def test_pagina_de_outro_set_com_o_mesmo_numero_e_recusada(set_name, number, url):
    assert not _product_matches(url, "<title>x</title>", number, set_name)


@pytest.mark.parametrize("set_name,number,url", PAGINA_DO_SET_CERTO)
def test_pagina_do_set_certo_continua_aceita(set_name, number, url):
    assert _product_matches(url, "<title>x</title>", number, set_name)


def test_product_id_igual_aceita_mesmo_com_nome_de_set_divergente():
    # "SM Base Set" no tcgcsv é "sun-&-moon" no PriceCharting: o nome não casa,
    # mas a página declara o MESMO productId do catálogo — identidade provada.
    url = PC + "pokemon-sun-&-moon/lapras-gx-151"
    assert not _product_matches(url, "", "151", "SM Base Set")
    assert _product_matches(url, "", "151", "SM Base Set",
                            tcg_product_id="133", page_product_id="133")
    # productId diferente NÃO resgata uma página de outro set.
    assert not _product_matches(
        PC + "pokemon-chaos-rising/mega-greninja-ex-116", "", "116",
        "EX FireRed & LeafGreen", tcg_product_id="90723", page_product_id="693517")


def test_subset_que_divide_slug_e_numeracao_com_o_set_pai_so_passa_por_product_id():
    # "Celebrations: Classic Collection" mora no MESMO slug do Celebrations e
    # os números colidem (no run de 2026-09-21, Kyogre #3, Dark Gyarados #8 e
    # M Rayquaza EX #76 da Classic Collection foram aceitos pra cartas de
    # outros sets). Por isso "classic"/"collection" NÃO são ruído de set — o
    # que também preserva "Legendary Collection" ≠ "Legendary Treasures".
    url = PC + "pokemon-celebrations/charizard-4"
    assert not _product_matches(url, "", "4", "Celebrations: Classic Collection")
    assert _product_matches(url, "", "4", "Celebrations: Classic Collection",
                            tcg_product_id="250303", page_product_id="250303")
    assert not _product_matches(PC + "pokemon-legendary-treasures/x-45", "",
                                "45", "Legendary Collection")


def test_shadowless_nao_aceita_a_pagina_unlimited():
    # Carta do catálogo é Shadowless; a página sem o qualificador é a unlimited
    # (outro censo, outro preço). A página certa traz o qualificador no slug.
    assert not _product_matches(PC + "pokemon-base-set/pikachu-58", "", "058",
                                "Base Set (Shadowless)")
    assert _product_matches(PC + "pokemon-base-set/bulbasaur-shadowless-44", "",
                            "44", "Base Set (Shadowless)")


def test_sem_set_informado_mantem_o_guard_so_de_numero():
    # Compatibilidade: chamadas antigas (sem set) seguem valendo pelo número.
    assert _product_matches(PC + "pokemon-obsidian-flames/charizard-ex-223",
                            "<title>x</title>", "223")


SEARCH_MESMO_NUMERO = f"""
<table id="games_table"><tbody>
<tr><td class="title"><a href="{PC}pokemon-chaos-rising/mega-greninja-ex-116"> Mega Greninja ex #116</a></td></tr>
<tr><td class="title"><a href="{PC}pokemon-firered-&-leafgreen/zapdos-ex-116"> Zapdos ex #116</a></td></tr>
</tbody></table>"""


def test_resultado_de_busca_pula_a_linha_de_outro_set():
    assert (pick_search_result(SEARCH_MESMO_NUMERO, "116", "EX FireRed & LeafGreen")
            == PC + "pokemon-firered-&-leafgreen/zapdos-ex-116")
    assert pick_search_result(SEARCH_MESMO_NUMERO, "116", "XY - Flashfire") is None


# ── Preço US$ 0.00 não é preço ───────────────────────────────────────────────

def test_preco_psa10_zero_vira_none():
    # 5 linhas do run saíram com "PSA 10 US$ 0.00" e "prêmio 0.0×": a página
    # escreve $0.00 quando não há venda — é ausência de dado, não preço.
    body = '<td id="manual_only_price"><span class="price js-price">$0.00</span></td>'
    assert parse_psa10_price(body) is None
    full = ('<div id="full-prices"><table><tr><td>PSA 10</td>'
            '<td class="price js-price">$0.00</td></tr></table></div>')
    assert parse_psa10_price(full) is None


def test_preco_cru_zero_vira_none():
    assert parse_raw_price('<td id="used_price"><span>$0.00</span></td>') is None


# ── Cache gravado pelo guard antigo não pode sobreviver ──────────────────────

def _grava_cache(tmp_path, monkeypatch, set_name, number, payload):
    monkeypatch.setattr(psa10, "CACHE_DIR", tmp_path)
    psa10._cache_path("Carta", set_name, number).write_text(json.dumps(
        {**payload, "status": "ok", "_cached_on": date.today().isoformat()}),
        encoding="utf-8")


def test_cache_com_pagina_de_outro_set_e_descartado(tmp_path, monkeypatch):
    _grava_cache(tmp_path, monkeypatch, "EX FireRed & LeafGreen", "116", {
        "usd": 468.36, "tcg_product_id": "693517",
        "url": PC + "pokemon-chaos-rising/mega-greninja-ex-116"})
    assert psa10._cache_get("Carta", "EX FireRed & LeafGreen", "116") is None


def test_cache_com_preco_zero_e_descartado(tmp_path, monkeypatch):
    _grava_cache(tmp_path, monkeypatch, "Platinum", "8", {
        "usd": 0.0, "tcg_product_id": "125076",
        "url": PC + "pokemon-platinum/gardevoir-8"})
    assert psa10._cache_get("Carta", "Platinum", "8") is None


def test_cache_bom_continua_valendo(tmp_path, monkeypatch):
    _grava_cache(tmp_path, monkeypatch, "SWSH07: Evolving Skies", "205", {
        "usd": 564.08, "tcg_product_id": "246696",
        "url": PC + "pokemon-evolving-skies/leafeon-vmax-205"})
    hit = psa10._cache_get("Carta", "SWSH07: Evolving Skies", "205")
    assert hit and hit["usd"] == 564.08
