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


# ── Cobertura: links com &amp; e slugs com hífen dentro da palavra ───────────
# Run de 2026-09-21: 27 linhas "sem match confiável" (Charmander #168 do 151,
# Gengar #27 DP, Ditto #4 FRLG…). Causa: o href da linha de resultado vem
# HTML-escapado ("pokemon-scarlet-&amp;-violet-151/…") e era aberto cru; e
# "fire-red-&-leaf-green" não casava token a token com "FireRed & LeafGreen".

SEARCH_AMP = """
<table id="games_table"><tbody>
<tr><td class="title"><a href="https://www.pricecharting.com/game/pokemon-scarlet-&amp;-violet-151/charmander-168"> Charmander #168</a></td></tr>
<tr><td class="title"><a href="https://www.pricecharting.com/game/pokemon-japanese-scarlet-&amp;-violet-151/charmander-168"> Charmander #168</a></td></tr>
</tbody></table>"""


def test_link_da_busca_e_desescapado_antes_de_abrir():
    assert (pick_search_result(SEARCH_AMP, "168", "SV: Scarlet & Violet 151")
            == PC + "pokemon-scarlet-&-violet-151/charmander-168")


@pytest.mark.parametrize("set_name,number,url", [
    ("EX FireRed & LeafGreen", "4", PC + "pokemon-fire-red-&-leaf-green/ditto-4"),
    ("HeartGold SoulSilver", "4", PC + "pokemon-heartgold-&-soulsilver/gyarados-4"),
    ("Diamond and Pearl", "27", PC + "pokemon-diamond-&-pearl/gengar-27"),
    ("SV: Scarlet & Violet 151", "168", PC + "pokemon-scarlet-&-violet-151/charmander-168"),
])
def test_set_com_hifen_dentro_da_palavra_ou_ampersand_casa(set_name, number, url):
    assert _product_matches(url, "", number, set_name)


def test_edicao_japonesa_ou_coreana_do_mesmo_set_e_recusada():
    assert not _product_matches(PC + "pokemon-japanese-scarlet-&-violet-151/charmander-168",
                                "", "168", "SV: Scarlet & Violet 151")
    assert not _product_matches(PC + "pokemon-korean-jet-black-geist/gengar-27",
                                "", "27", "Diamond and Pearl")


def test_redirect_direto_para_variante_de_impressao_e_recusado():
    # Nit da revisão do #28: a busca pode redirecionar DIRETO pra página
    # "[1st Edition]" / "[Reverse Holo]" sem passar pela lista de resultados.
    # Catálogo sem qualificador = impressão comum; variante no slug reprova.
    assert not _product_matches(PC + "pokemon-base-set/charizard-1st-edition-4", "", "4", "Base Set")
    assert not _product_matches(PC + "pokemon-diamond-&-pearl/gengar-reverse-holo-27", "", "27", "Diamond and Pearl")
    assert _product_matches(PC + "pokemon-base-set/charizard-4", "", "4", "Base Set")


def test_product_id_igual_nao_resgata_variante_de_impressao():
    # Revisão de 2026-09-22: o atalho por productId respondia ANTES do guard de
    # variante. Página "[1st Edition]" que aponte pro productId da unlimited
    # continua sendo outra impressão (outro censo, outro preço) — reprova.
    assert not _product_matches(PC + "pokemon-base-set/charizard-1st-edition-4", "",
                                "4", "Base Set", tcg_product_id="42382",
                                page_product_id="42382")
