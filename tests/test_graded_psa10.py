"""Contratos do modo graded: componente de Preço medido no slab PSA 10.

Tudo offline: as funções de parse recebem HTML fixo (recortes fiéis à estrutura
real do PriceCharting, verificada em 2026-09-01) e as de score são puras.
"""
from datetime import date

import pytest

from outlook import psa10
from outlook.report import ranking_markdown
from outlook.scoring import (PSA10_ILLIQUID_CAP, PSA10_MIN_SALES_PER_MONTH,
                             apply_psa10, price_points, price_points_psa10,
                             score_card)

# ── Faixas de preço PSA 10 ───────────────────────────────────────────────────


@pytest.mark.parametrize("usd,esperado", [
    (9.99, 5),      # abaixo de $15: sem liquidez, mesmo em slab
    (30.0, 12),
    (100.0, 20),
    (200.0, 25),    # sweet spot do slab ($120-360)
    (359.99, 25),
    (500.0, 18),    # já caro
    (1500.0, 12),   # já precificado
])
def test_faixas_psa10(usd, esperado):
    assert price_points_psa10(usd) == esperado


def test_faixas_psa10_sao_as_raw_reancoradas_em_3x():
    """A régua graded é a MESMA lógica das faixas raw, deslocada 3× (mediana
    observada do múltiplo PSA 10/raw = 3.3×). O sweet spot raw $40-120 vira
    $120-360 no slab — mesma nota máxima."""
    assert price_points(60.0) == 25 and price_points_psa10(180.0) == 25
    assert price_points(20.0) == 20 and price_points_psa10(60.0) == 20
    assert price_points(200.0) == 18 and price_points_psa10(600.0) == 18


# ── Teto de iliquidez ────────────────────────────────────────────────────────


def test_slab_iliquido_e_tetado():
    # Mesmo no sweet spot, um slab que vende 1x/mês não realiza o preço de tabela.
    assert price_points_psa10(200.0, sales_per_month=1.0) == PSA10_ILLIQUID_CAP
    assert price_points_psa10(200.0, sales_per_month=30.0) == 25


def test_liquidez_desconhecida_nao_teta():
    """Sem dado NÃO é sinal de iliquidez — não pode ser punido como se fosse."""
    assert price_points_psa10(200.0, sales_per_month=None) == 25


def test_teto_nunca_aumenta_a_nota():
    """O teto é `min`, não substituição: faixa já abaixo dele não sobe.

    $10 vale 5 pontos (abaixo do teto 12); slab ilíquido tem que continuar em
    5, nunca ser 'promovido' a 12 pelo teto.
    """
    assert price_points_psa10(10.0, sales_per_month=0.5) == 5


def test_corte_de_liquidez_na_fronteira():
    assert price_points_psa10(200.0, PSA10_MIN_SALES_PER_MONTH) == 25
    assert (price_points_psa10(200.0, PSA10_MIN_SALES_PER_MONTH - 0.1)
            == PSA10_ILLIQUID_CAP)


# ── apply_psa10: aplicação sobre uma carta já pontuada ───────────────────────

CARD = {"id": "1", "name": "Charizard ex", "number": "223",
        "rarity": "Special Illustration Rare"}
SET_META = {"id": "s1", "name": "SV03: Obsidian Flames", "series": "Scarlet & Violet",
            "releaseDate": "2023-08-11"}


def _carta_base():
    return score_card(CARD, SET_META, 108.59, today=date(2026, 9, 1))


def test_apply_psa10_remede_o_preco_no_slab():
    sc = _carta_base()
    raw_pts = sc.pts_price
    apply_psa10(sc, 772.50, 30.0, "ok")
    assert sc.psa10_usd == 772.50
    assert sc.pts_price == 18          # $772 cai na faixa $360-900
    assert sc.pts_price != raw_pts     # a régua mudou de fato
    assert sc.score == (sc.pts_character + sc.pts_rarity
                        + sc.pts_supply + sc.pts_price)


def test_sem_psa10_mantem_regua_raw_e_declara_o_motivo():
    sc = _carta_base()
    raw_pts = sc.pts_price
    apply_psa10(sc, None, None, "sem match confiável")
    assert sc.pts_price == raw_pts     # não zera, não inventa
    assert sc.psa10_usd is None
    assert any("sem preço PSA 10" in n for n in sc.notes)


def test_iliquidez_vira_nota_visivel():
    sc = _carta_base()
    apply_psa10(sc, 200.0, 1.0, "ok")
    assert sc.pts_price == PSA10_ILLIQUID_CAP
    assert any("ilíquido" in n for n in sc.notes)


def test_score_continua_somando_4_componentes_de_0_25():
    sc = _carta_base()
    apply_psa10(sc, 200.0, 30.0, "ok")
    for pts in (sc.pts_character, sc.pts_rarity, sc.pts_supply, sc.pts_price):
        assert 0 <= pts <= 25
    assert sc.score <= 100


# ── Parsers do PriceCharting (HTML fiel à estrutura real) ────────────────────

FULL_PRICES = """
<div id="full-prices"><table>
  <tr><td> Ungraded </td><td><span class="js-price">$109.13</span></td></tr>
  <tr><td> Grade 9 </td><td><span class="js-price">$131.30</span></td></tr>
  <tr><td> PSA 10 </td><td><span class="js-price">$772.50</span></td></tr>
  <tr><td> BGS 10 </td><td><span class="js-price">$1,004.00</span></td></tr>
</table></div>
"""

PRICE_DATA = """
<table id="price_data">
  <td id="used_price">$109.13</td><td id="complete_price">$86.38</td>
  <td id="new_price">$92.50</td><td id="graded_price">$131.30</td>
  <td id="box_only_price">$157.62</td><td id="manual_only_price">$772.50</td>
  <td>30 sales per month</td><td>4 sales per month</td>
  <td>13 sales per month</td><td>60 sales per month</td>
  <td>4 sales per month</td><td>2 sales per week</td>
</table>
"""


def test_parse_preco_psa10_da_tabela_completa():
    assert psa10.parse_psa10_price(FULL_PRICES) == 772.50


def test_parse_preco_psa10_cai_na_tabela_principal():
    assert psa10.parse_psa10_price(PRICE_DATA) == 772.50


def test_parse_preco_com_milhar():
    body = '<div id="full-prices"><table><tr><td> PSA 10 </td>' \
           '<td><span class="js-price">$1,250.00</span></td></tr></table></div>'
    assert psa10.parse_psa10_price(body) == 1250.0


def test_pagina_sem_psa10_devolve_none():
    body = '<div id="full-prices"><table><tr><td> Ungraded </td>' \
           '<td><span class="js-price">$5.00</span></td></tr></table></div>'
    assert psa10.parse_psa10_price(body) is None


def test_vendas_por_mes_le_a_coluna_do_psa10_e_normaliza_periodo():
    # A 6ª célula de volume é a do PSA 10: "2 sales per week" -> 8.7/mês.
    assert psa10.parse_psa10_sales_per_month(PRICE_DATA) == 8.7


def test_vendas_sem_tabela_devolve_none():
    assert psa10.parse_psa10_sales_per_month("<html></html>") is None


def test_vendas_com_menos_colunas_que_o_psa10_devolve_none():
    """Volume parcial não pode ser lido como se fosse do PSA 10."""
    body = ('<table id="price_data"><td>30 sales per month</td>'
            '<td>4 sales per month</td></table>')
    assert psa10.parse_psa10_sales_per_month(body) is None


def test_match_exige_o_numero_da_carta():
    url = "https://www.pricecharting.com/game/pokemon-obsidian-flames/charizard-ex-223"
    assert psa10._product_matches(url, "<title>x</title>", "223")
    # número ausente na URL e no título = não é a carta; nunca chuta
    outra = "https://www.pricecharting.com/game/pokemon-obsidian-flames/pikachu-999"
    assert not psa10._product_matches(outra, "<title>Pikachu #999</title>", "223")


def test_match_aceita_numero_com_barra_e_zero_a_esquerda():
    url = "https://www.pricecharting.com/game/pokemon-go/mewtwo-v-72"
    assert psa10._product_matches(url, "<title>x</title>", "072/078")


# ── Tabela de entrega ────────────────────────────────────────────────────────


def test_tabela_graded_mostra_psa10_liquidez_e_raw():
    sc = _carta_base()
    sc.tcg_url = "https://tcg.example/x"
    apply_psa10(sc, 772.50, 30.0, "ok")
    md = ranking_markdown([sc], 1, graded=True)
    assert "PSA 10 US$" in md and "Vendas/mês" in md and "Raw US$" in md
    assert "772.50" in md and "108.59" in md      # slab e raw, ambos visíveis
    assert "MODO GRADED" in md


def test_tabela_graded_declara_carta_sem_psa10():
    sc = _carta_base()
    sc.tcg_url = "https://tcg.example/x"
    apply_psa10(sc, None, None, "sem match confiável")
    md = ranking_markdown([sc], 1, graded=True)
    assert "n/d (sem match confiável)" in md


def test_tabela_normal_nao_ganha_colunas_do_modo_graded():
    sc = _carta_base()
    sc.tcg_url = "https://tcg.example/x"
    md = ranking_markdown([sc], 1)
    assert "PSA 10 US$" not in md and "MODO GRADED" not in md
