"""Contrato do link de compra PSA 10 no eBay (funcao pura, offline)."""
from urllib.parse import parse_qs, urlparse

from outlook.availability import ebay_psa10_url


def _q(url):
    return parse_qs(urlparse(url).query)


def test_query_tem_nome_numero_set_e_psa_10():
    q = _q(ebay_psa10_url("Umbreon V (Alternate Full Art)",
                          "SWSH07: Evolving Skies", "189"))
    nkw = q["_nkw"][0]
    # qualificador entre parenteses sai (mesma regra da coleta); numero e set ficam
    assert "alternate" not in nkw.lower()
    assert "umbreon v" in nkw.lower()
    assert "189" in nkw
    assert "evolving skies" in nkw.lower()
    assert "swsh07" not in nkw.lower()      # prefixo de era removido
    assert "psa 10" in nkw.lower()


def test_filtros_fixos_categoria_bin_e_ordem_por_preco():
    q = _q(ebay_psa10_url("Charizard ex", "SV03: Obsidian Flames", "223"))
    assert q["_sacat"] == ["183454"]        # CCG Individual Cards
    assert q["LH_BIN"] == ["1"]             # so Buy It Now
    assert q["_sop"] == ["15"]              # preco + frete, menor primeiro


def test_numero_com_barra_e_zero_a_esquerda_normaliza():
    # "072/078" -> "72": mesma normalizacao de _clean_number usada na coleta.
    assert "72" in _q(ebay_psa10_url("Mewtwo V", "Pokemon GO", "072/078"))["_nkw"][0]


def test_set_com_e_comercial_fica_utilizavel():
    url = ebay_psa10_url("Snorlax VMAX", "SWSH01: Sword & Shield Base Set", "206")
    assert "sword" in _q(url)["_nkw"][0].lower()
    assert "&_sacat=" in url                # o "&" do set nao quebrou a querystring
