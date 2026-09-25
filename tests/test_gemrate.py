"""GemRate como fonte do censo PSA (2026-09-24): pop de PSA 10 oficial e diário.

Por que existe: o censo do PriceCharting (`VGPC.pop_data`) é uma foto mensal
que atrasa MESES em set moderno — N's Zoroark ex #286 saía com 1.046 PSA 10
quando a PSA já tinha 3.318 (3,2×); Sylveon V #184 com 1/6 quando o real era
7.163/13.906. A GemRate publica o pop da PSA por carta, sem login, e o número
bate com o Pop Report oficial. Fixtures abaixo = formato REAL das páginas
(`var RowData = JSON.parse('[...]')` na página por Pokémon; `let setsData =
[...]` no índice), com registros reduzidos aos campos que usamos.
"""
import json
from datetime import date

import pytest

from outlook import gemrate
from outlook.gemrate import (GemratePop, match_record, parse_player_page,
                             parse_sets_index, player_query)
from outlook.report import ranking_markdown
from outlook.scoring import apply_lowpop, pop_trust_issue, score_card


def _rec(**kw):
    base = {"category": "TCG", "year": "2021", "set_name": "Pokemon Sword & Shield Evolving Skies",
            "name": "Full Art/Sylveon V", "card_number": "184", "parallel": "Base",
            "gems": 7163, "psa_9_plus": 12523, "total": 13906, "cert_number": "157068546"}
    base.update(kw)
    return base


def _player_html(records):
    # A página embute a lista como STRING JS entre aspas simples: aspas simples
    # dentro do JSON viram \\u0027 (é assim que a GemRate escapa "N's").
    payload = json.dumps(records).replace("'", "\\u0027")
    return ("<html><head></head><body><script>\n\tvar RowData = JSON.parse('" + payload
            + "');\n\tvar other = 1;</script></body></html>")


# ── Parsers ──────────────────────────────────────────────────────────────────

def test_parse_player_page_le_o_rowdata_e_desescapa_apostrofo():
    recs = parse_player_page(_player_html([_rec(name="N's Zoroark EX", set_name="Pokemon Asc EN-Ascended Heroes",
                                                year="2026", card_number="286", gems=3318, total=4985)]))
    assert len(recs) == 1 and recs[0]["name"] == "N's Zoroark EX" and recs[0]["gems"] == 3318


def test_parse_player_page_sem_rowdata_devolve_lista_vazia():
    assert parse_player_page("<html>nada</html>") == []
    assert parse_player_page("var RowData = JSON.parse('{quebrado');") == []


def test_parse_sets_index_lista_sets_pokemon():
    html = ("<script>let setsData = [" + json.dumps({"category": "TCG", "set_name": "Pokemon Aquapolis", "year": "2003",
            "set_link": "https://www.gemrate.com/universal-pop-report/abc-2003%20Pokemon%20Aquapolis-TCG", "psa_grades": 5})
            + "," + json.dumps({"category": "Football", "set_name": "Prizm", "year": "2017", "set_link": "x"}) + "];</script>")
    sets = parse_sets_index(html)
    assert [s["set_name"] for s in sets] == ["Pokemon Aquapolis"]


# ── Query por Pokémon ────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,q", [
    ("Sylveon V (Alternate Full Art)", "Sylveon V"),
    ("Espeon (H9)", "Espeon"),
    ("N's Zoroark ex", "N's Zoroark ex"),
    ("Mimikyu -160/091", "Mimikyu"),          # quirk do catálogo TCGPlayer
    ("Umbreon (61)", "Umbreon"),
])
def test_player_query_e_o_nome_base_sem_qualificador(name, q):
    assert player_query(name) == q


# ── Match registro ↔ carta do catálogo (precisão > cobertura) ────────────────

def test_match_moderno_por_numero_ano_set_e_paralelo_base():
    recs = [_rec(), _rec(parallel="Italian", gems=16, total=85), _rec(parallel="Inverted Back", gems=1, total=7)]
    m = match_record(recs, "Sylveon V (Alternate Full Art)", "SWSH07: Evolving Skies", "184", 2021, "Ultra Rare")
    assert m == GemratePop(pop10=7163, psa9_plus=12523, total=13906, record=recs[0])


def test_match_numero_h_do_ecard_e_nome_com_sufixo_holo():
    recs = [_rec(year="2003", set_name="Pokemon Aquapolis", name="Espeon-Holo", card_number="H9",
                 gems=105, psa_9_plus=401, total=1303),
            _rec(year="2003", set_name="Pokemon Aquapolis", name="Espeon-Holo", card_number="H9",
                 parallel="Italian", gems=1, total=18)]
    m = match_record(recs, "Espeon (H9)", "Aquapolis", "H09", 2003, "Holo Rare")
    assert m.pop10 == 105 and m.total == 1303


def test_match_holo_rare_prefere_o_registro_holo_e_recusa_theme_deck_e_reverse():
    recs = [_rec(year="2009", set_name="Pokemon Platinum", name="Gardevoir-Reverse Foil", card_number="8", gems=2, total=56),
            _rec(year="2009", set_name="Pokemon Platinum", name="Gardevoir", card_number="8", gems=0, total=1),
            _rec(year="2009", set_name="Pokemon Platinum", name="Gardevoir", card_number="8",
                 parallel="Rebellion Theme Deck", gems=0, total=14),
            _rec(year="2009", set_name="Pokemon Platinum", name="Gardevoir-Holo", card_number="8", gems=8, total=171)]
    m = match_record(recs, "Gardevoir", "Platinum", "8", 2009, "Holo Rare")
    assert m.pop10 == 8 and m.total == 171 and m.record["name"] == "Gardevoir-Holo"
    # Sem "Holo" na raridade, o registro comum é o certo; a reverse nunca.
    m2 = match_record(recs, "Gardevoir", "Platinum", "8", 2009, "Rare")
    assert m2.record["name"] == "Gardevoir" and m2.record["parallel"] == "Base"


def test_match_recusa_ano_set_ou_numero_diferentes():
    recs = [_rec()]
    assert match_record(recs, "Sylveon V", "SWSH07: Evolving Skies", "184", 2022, "Ultra Rare") is None   # ano
    assert match_record(recs, "Sylveon V", "SWSH08: Fusion Strike", "184", 2021, "Ultra Rare") is None    # set
    assert match_record(recs, "Sylveon V", "SWSH07: Evolving Skies", "18", 2021, "Ultra Rare") is None    # número
    assert match_record(recs, "Glaceon V", "SWSH07: Evolving Skies", "184", 2021, "Ultra Rare") is None   # nome


def test_match_151_nao_casa_com_o_set_base_e_vice_versa():
    r151 = _rec(year="2023", set_name="Pokemon Scarlet & Violet 151", name="Charizard EX", card_number="199")
    rbase = _rec(year="2023", set_name="Pokemon Scarlet and Violet", name="Charizard EX", card_number="199")
    assert match_record([rbase], "Charizard ex", "SV: Scarlet & Violet 151", "199", 2023, "Double Rare") is None
    assert match_record([r151], "Charizard ex", "SV01: Scarlet & Violet Base Set", "199", 2023, "Double Rare") is None
    assert match_record([r151, rbase], "Charizard ex", "SV: Scarlet & Violet 151", "199", 2023, "Double Rare").record is r151


@pytest.mark.parametrize("cat_set,gr_set,year", [
    ("ME: Ascended Heroes", "Pokemon Asc EN-Ascended Heroes", 2026),
    ("ME01: Mega Evolution", "Pokemon Mega Evolution", 2025),
    ("XY - Flashfire", "Pokemon XY Flashfire", 2014),
    ("EX Dragon", "Pokemon EX Dragon", 2003),
    ("Call of Legends", "Pokemon Call of Legends", 2011),
    ("SV: Paldean Fates", "Pokemon Scarlet & Violet Paldean Fates", 2024),
    ("Celebrations: Classic Collection", "Pokemon Celebrations Classic Collection", 2021),
])
def test_match_nomes_de_set_reais_da_gemrate(cat_set, gr_set, year):
    recs = [_rec(year=str(year), set_name=gr_set, name="Pikachu", card_number="7")]
    assert match_record(recs, "Pikachu", cat_set, "7", year, "Rare") is not None


def test_match_ambiguidade_devolve_none():
    recs = [_rec(name="Gardevoir", gems=1), _rec(name="Gardevoir", gems=2)]
    assert match_record(recs, "Gardevoir", "SWSH07: Evolving Skies", "184", 2021, "Rare") is None


# ── Cache + fetch (rede simulada) ────────────────────────────────────────────

def test_fetch_player_usa_cache_por_7_dias(tmp_path, monkeypatch):
    monkeypatch.setattr(gemrate, "CACHE_DIR", tmp_path)
    calls = []

    def fake_get(url):
        calls.append(url)
        return _player_html([_rec()])
    monkeypatch.setattr(gemrate, "_get", fake_get)
    assert gemrate.fetch_player("Sylveon V")[0]["gems"] == 7163
    assert gemrate.fetch_player("Sylveon V")[0]["gems"] == 7163
    assert len(calls) == 1 and "player=Sylveon+V" in calls[0] and "grader=psa" in calls[0]


def test_lookup_devolve_none_sem_rede_e_nunca_inventa(monkeypatch, tmp_path):
    monkeypatch.setattr(gemrate, "CACHE_DIR", tmp_path)

    def boom(url):
        raise OSError("rede")
    monkeypatch.setattr(gemrate, "_get", boom)
    assert gemrate.lookup("Sylveon V", "SWSH07: Evolving Skies", "184", 2021, "Ultra Rare") is None


# ── Integração no modo low pop ───────────────────────────────────────────────

CARD = {"id": "246700", "name": "Sylveon V (Alternate Full Art)", "number": "184", "rarity": "Ultra Rare"}
META = {"id": "swsh7", "name": "SWSH07: Evolving Skies", "series": "Sword & Shield", "releaseDate": "2021-08-27"}
PC_PAGE = {"usd": 399.57, "sales_per_month": 30.0, "raw_usd": 199.09,
           "pop_psa": [0, 0, 0, 0, 0, 0, 0, 1, 4, 1], "pop_cgc": [0] * 10,
           "tcg_product_id": "246700", "status": "ok"}


def _carta():
    return score_card(CARD, META, 199.09, today=date(2026, 9, 24))


def test_lowpop_prefere_o_pop_gemrate_e_declara_a_fonte():
    sc = _carta()
    apply_lowpop(sc, {**PC_PAGE, "gemrate": GemratePop(7163, 12523, 13906, _rec())}, today=date(2026, 9, 24))
    assert sc.pop_source == "gemrate" and sc.pop_psa10 == 7163 and sc.pop_total == 13906
    assert sc.pop_issue is None and sc.pts_scarcity == 7           # faixa ≤10.000
    assert not any("página fina" in n for n in sc.notes)


def test_lowpop_sem_gemrate_cai_no_pricecharting_com_nota_de_defasagem():
    sc = _carta()
    apply_lowpop(sc, {**PC_PAGE, "gemrate": None}, today=date(2026, 9, 24))
    assert sc.pop_source == "pricecharting" and sc.pop_psa10 == 1
    assert any("PriceCharting" in n and "defasado" in n for n in sc.notes)


def test_gemrate_com_zero_psa10_nao_pontua_escassez_maxima():
    # Handoff item 2.3 (nit do #28): pop10 = 0 não é "escassez 25", é "ninguém
    # gradou ainda" — vai pro balde de validação com o motivo.
    sc = _carta()
    apply_lowpop(sc, {**PC_PAGE, "gemrate": GemratePop(0, 0, 3, _rec(gems=0, psa_9_plus=0, total=3))},
                 today=date(2026, 9, 24))
    assert sc.pop_issue and "nenhuma PSA 10" in sc.pop_issue
    assert sc.pts_scarcity == sc.pts_supply


def test_gemrate_censo_pequeno_e_real_nao_e_pagina_fina():
    assert pop_trust_issue([0] * 9 + [3], 1.0, age_months=200, source="gemrate") is None
    assert "página fina" in pop_trust_issue([0] * 9 + [3], 1.0, age_months=200)


def test_tabela_mostra_a_fonte_do_censo():
    a, b = _carta(), _carta()
    apply_lowpop(a, {**PC_PAGE, "gemrate": GemratePop(7163, 12523, 13906, _rec())})
    apply_lowpop(b, {**PC_PAGE, "gemrate": None})
    md = ranking_markdown([a, b], 10, lowpop=True)
    assert "7,163 / 13,906 (52%) PSA" in md and "1 / 6 (17%) PC" in md


# ── Nomenclatura REAL da GemRate (sonda 2026-09-24) ──────────────────────────

def test_set_moderno_codigo_en_e_paralelo_igual_a_raridade():
    recs = [_rec(year="2026", set_name="Pokemon Asc EN-Ascended Heroes", name="N's Zoroark EX", card_number="286",
                 parallel="Special Illustration Rare", gems=3318, psa_9_plus=4819, total=4985),
            _rec(year="2026", set_name="Pokemon Spanish Asc ES-Ascended Heroes", name="N's Zoroark EX", card_number="286",
                 parallel="Special Illustration Rare", gems=2, total=3),
            _rec(year="2026", set_name="Pokemon Latin American Asc La-Ascended Heroes", name="N's Zoroark EX",
                 card_number="286", parallel="Special Illustration Rare", gems=0, total=1)]
    m = match_record(recs, "N's Zoroark ex", "ME: Ascended Heroes", "286", 2026, "Special Illustration Rare")
    assert m.pop10 == 3318 and m.total == 4985
    # Raridade diferente da do paralelo (o registro é de OUTRA variante) → nada.
    assert match_record(recs, "N's Zoroark ex", "ME: Ascended Heroes", "286", 2026, "Double Rare") is None


def test_151_en_vs_idiomas_e_promos_de_tin():
    recs = [_rec(year="2023", set_name="Pokemon Mew EN-151", name="Blastoise EX", card_number="200",
                 parallel="Special Illustration Rare", gems=18934, total=59000),
            _rec(year="2023", set_name="Pokemon Italian Mew It-151", name="Blastoise EX", card_number="200",
                 parallel="Special Illustration Rare", gems=120, total=300),
            _rec(year="2024", set_name="Pokemon Mew EN-151", name="Blastoise EX", card_number="200",
                 parallel="151 5-Pack Mini Tin", gems=5, total=9)]
    m = match_record(recs, "Blastoise ex", "SV: Scarlet & Violet 151", "200", 2023, "Special Illustration Rare")
    assert m.pop10 == 18934
    assert match_record(recs, "Blastoise ex", "SV01: Scarlet & Violet Base Set", "200", 2023, "Special Illustration Rare") is None


def test_base_set_e_pokemon_game_na_gemrate():
    recs = [_rec(year="1999", set_name="Pokemon Game", name="Charizard-Holo", card_number="4", gems=100, total=5000),
            _rec(year="1999", set_name="Pokemon Game", name="Charizard-Holo", card_number="4", parallel="1st Edition", gems=1, total=3),
            _rec(year="1999", set_name="Pokemon Game", name="Charizard-Holo", card_number="4", parallel="Shadowless", gems=9, total=90),
            _rec(year="2000", set_name="Pokemon Game Base II", name="Charizard-Holo", card_number="4", gems=7, total=70)]
    assert match_record(recs, "Charizard", "Base Set", "4", 1999, "Holo Rare").pop10 == 100
    assert match_record(recs, "Charizard", "Base Set (Shadowless)", "4", 1999, "Holo Rare").pop10 == 9
    assert match_record(recs, "Charizard", "Base Set 2", "4", 2000, "Holo Rare").pop10 == 7


def test_firered_leafgreen_casa_por_tokens_colados_e_gym_challenge_holo_no_paralelo():
    frlg = [_rec(year="2004", set_name="Pokemon EX Fire Red & Leaf Green", name="Ditto-Holo", card_number="4", gems=3, total=30)]
    assert match_record(frlg, "Ditto", "EX FireRed & LeafGreen", "4", 2004, "Holo Rare").pop10 == 3
    gym = [_rec(year="2000", set_name="Pokemon Gym Challenge", name="Blaine's Charizard", card_number="2", parallel="Holo", gems=40, total=900),
           _rec(year="2000", set_name="Pokemon Gym Challenge", name="Blaine's Charizard", card_number="2", parallel="Holo-1st Edition", gems=4, total=90)]
    assert match_record(gym, "Blaine's Charizard", "Gym Challenge", "2", 2000, "Holo Rare").pop10 == 40


def test_neo_genesis_1st_edition_e_set_separado_e_nao_casa_com_o_normal():
    recs = [_rec(year="2000", set_name="Pokemon Neo Genesis 1st Edition", name="Lugia-Holo", card_number="9", gems=1, total=2)]
    assert match_record(recs, "Lugia", "Neo Genesis", "9", 2000, "Holo Rare") is None


# ── Achados da revisão independente (2026-09-24) ─────────────────────────────

def test_variante_holo_errada_nunca_e_aceita_mesmo_sendo_a_unica():
    so_holo = [_rec(year="2009", set_name="Pokemon Platinum", name="Gardevoir-Holo", card_number="8", gems=8, total=171)]
    so_plain = [_rec(year="2009", set_name="Pokemon Platinum", name="Gardevoir", card_number="8", gems=0, total=1)]
    assert match_record(so_holo, "Gardevoir", "Platinum", "8", 2009, "Rare") is None
    assert match_record(so_plain, "Gardevoir", "Platinum", "8", 2009, "Holo Rare") is None


def test_set_so_de_era_exige_as_mesmas_palavras_de_era():
    swsh = _rec(year="2020", set_name="Pokemon Sword & Shield", name="Zacian V", card_number="138")
    assert match_record([swsh], "Zacian V", "SWSH01: Sword & Shield Base Set", "138", 2020, "Ultra Rare") is not None
    # Mesmo ano e número, mas era diferente no nome: [] == [] não prova nada.
    assert match_record([swsh], "Zacian V", "SM: Sun & Moon Base Set", "138", 2020, "Ultra Rare") is None
    assert match_record([_rec(year="2014", set_name="Pokemon XY", name="Pikachu", card_number="42")],
                        "Pikachu", "XY", "42", 2014, "Common") is not None


def test_parse_player_page_barra_escapada_antes_da_aspa_final():
    # Payload termina com "\\" (barra literal) antes da aspa que fecha a string JS.
    html = "var RowData = JSON.parse('[{\"category\": \"TCG\", \"name\": \"x\\\\\"}]');"
    assert parse_player_page(html)[0]["name"] == "x\\"


# ── Run canônico de 2026-09-24 (543 GemRate / 167 PC): 3 causas dos 167 ──────
# Diagnóstico carta a carta (tabela × cache da GemRate): 118 caíram na regra
# holo estrita em raridade SEMPRE-foil (ex/LV.X/Prime/Legend/Secret vêm como
# "-Holo" na GemRate e como "Ultra Rare"/"Secret Rare" no catálogo), 60 em
# nome de set fora do mapa (Platinum, Shiny Vault, Trainer Gallery, Galarian
# Gallery, "SM Base Set", "Team Rocket"), 10 no quirk "Ditto - 039/113 (…)".

@pytest.mark.parametrize("rarity", ["Ultra Rare", "Secret Rare", "Rainbow Rare",
                                    "Shiny Holo Rare", "Amazing Rare", "Hyper Rare"])
def test_raridade_sempre_foil_aceita_o_registro_holo_da_gemrate(rarity):
    recs = [_rec(year="2010", set_name="Pokemon Heartgold & Soulsilver Undaunted",
                 name="Umbreon-Holo", card_number="86", gems=83, total=5346),
            _rec(year="2010", set_name="Pokemon Heartgold & Soulsilver Undaunted",
                 name="Umbreon-Holo", card_number="86", parallel="Italian", gems=2, total=52)]
    m = match_record(recs, "Umbreon (Prime)", "Undaunted", "86", 2010, rarity)
    assert m is not None and m.pop10 == 83


def test_raridade_simples_continua_estrita_no_holo():
    # A regra da revisão (2026-09-24) segue valendo onde a carta PODE ser
    # não-holo: "Rare"/"Common" com só o registro "-Holo" é outra impressão.
    so_holo = [_rec(year="2009", set_name="Pokemon Platinum", name="Gardevoir-Holo", card_number="8", gems=8, total=171)]
    assert match_record(so_holo, "Gardevoir", "Platinum", "8", 2009, "Rare") is None
    assert match_record(so_holo, "Gardevoir", "Platinum", "8", 2009, "Common") is None


def test_paralelo_que_e_rotulo_de_raridade_da_gemrate_nao_reprova():
    # XY: a GemRate põe a raridade dela no paralelo ("Ultra Rare" pra secret
    # rare); SM: "Secret" pra rainbow rare. O número já fixa a carta.
    xy = [_rec(year="2014", set_name="Pokemon XY Flashfire", name="M Charizard EX", card_number="107",
               parallel="Ultra Rare", gems=79, total=1200),
          _rec(year="2014", set_name="Pokemon XY Flashfire", name="M Charizard EX", card_number="107",
               parallel="Italian-Ultra Rare", gems=0, total=3)]
    assert match_record(xy, "M Charizard EX (Y) (Secret)", "XY - Flashfire", "107", 2014, "Secret Rare").pop10 == 79
    sm = [_rec(year="2018", set_name="Pokemon Sun & Moon Celestial Storm", name="Full Art/Rayquaza GX",
               card_number="177", parallel="Secret", gems=546, total=1523),
          _rec(year="2018", set_name="Pokemon Sun & Moon Celestial Storm", name="Full Art/Rayquaza GX",
               card_number="177", parallel="French-Secret", gems=4, total=14)]
    assert match_record(sm, "Rayquaza GX (Secret)", "SM - Celestial Storm", "177", 2018, "Rainbow Rare").pop10 == 546


@pytest.mark.parametrize("cat_set,gr_set,year", [
    ("Rising Rivals", "Pokemon Platinum Rising Rivals", 2009),
    ("Supreme Victors", "Pokemon Platinum Supreme Victors", 2009),
    ("Arceus", "Pokemon Platinum Arceus", 2009),
    ("Platinum", "Pokemon Platinum", 2009),
    ("Hidden Fates: Shiny Vault", "Pokemon Sun & Moon Hidden Fates", 2019),
    ("Shining Fates: Shiny Vault", "Pokemon Sword & Shield Shining Fates", 2021),
    ("SWSH11: Lost Origin Trainer Gallery", "Pokemon Sword & Shield Lost Origin", 2022),
    ("SWSH09: Brilliant Stars Trainer Gallery", "Pokemon Sword & Shield Brilliant Stars", 2022),
    ("SWSH: Crown Zenith: Galarian Gallery", "Pokemon Sword and Shield Crown Zenith", 2023),
    ("SM Base Set", "Pokemon Sun & Moon", 2017),
    ("Black and White", "Pokemon Black & White", 2011),
    ("Team Rocket", "Pokemon Rocket", 2000),
])
def test_match_mais_nomes_de_set_reais_da_gemrate(cat_set, gr_set, year):
    recs = [_rec(year=str(year), set_name=gr_set, name="Pikachu", card_number="7")]
    assert match_record(recs, "Pikachu", cat_set, "7", year, "Rare") is not None


def test_subset_nao_casa_com_outro_set_da_mesma_era():
    recs = [_rec(year="2022", set_name="Pokemon Sword & Shield Silver Tempest", name="Pikachu", card_number="TG05")]
    assert match_record(recs, "Pikachu", "SWSH11: Lost Origin Trainer Gallery", "TG05", 2022, "Rare") is None
    assert match_record(recs, "Pikachu", "SM Base Set", "TG05", 2022, "Rare") is None


@pytest.mark.parametrize("name,q", [
    ("Ditto - 039/113 (Pikachu)", "Ditto"),
    ("Rayquaza - 016/110 (Delta Species)", "Rayquaza"),
    ("Eevee - 068/113", "Eevee"),
])
def test_player_query_tira_o_quirk_numero_com_espaco_e_qualificador(name, q):
    assert player_query(name) == q


def test_shiny_holo_rare_do_shiny_vault_e_sempre_foil_e_nao_exige_holo_no_nome():
    # "Shiny Holo Rare" (SV##) traz "holo" no rótulo, mas não é a distinção
    # holo × não-holo do WotC: a GemRate lista "Full Art/Umbreon GX | Base".
    recs = [_rec(year="2019", set_name="Pokemon Sun & Moon Hidden Fates", name="Full Art/Umbreon GX",
                 card_number="SV69", gems=7084, total=13257),
            _rec(year="2019", set_name="Pokemon Sun & Moon Hidden Fates", name="Full Art/Umbreon GX",
                 card_number="SV69", parallel="Italian", gems=15, total=33)]
    assert match_record(recs, "Umbreon GX", "Hidden Fates: Shiny Vault", "SV69", 2019, "Shiny Holo Rare").pop10 == 7084


# ── Censo em formação (run 2026-09-24, 2ª leitura) ───────────────────────────
# A GemRate passou a ter o 30th Celebration (8 dias: Gengar ex 154 = 2 PSA 10 de
# 2 gradadas) e o Pitch Black (2 meses: pop mediana 3). "Pop 2" aí não é
# escassez, é que ninguém teve tempo de gradar — e foi pro #1 do ranking.
# Dado do snapshot: 8 dias → mediana 1,5; 2 meses → 3; 4 meses → 359; 6 → 3.074.

def test_gemrate_set_com_menos_de_3_meses_e_censo_em_formacao_e_vai_pro_balde():
    novo = {"id": "me30", "name": "ME: 30th Celebration", "series": "Mega Evolution", "releaseDate": "2026-09-16"}
    sc = score_card({"id": "1", "name": "Gengar ex", "number": "154", "rarity": "Special Illustration Rare"},
                    novo, 300.0, today=date(2026, 9, 24))
    apply_lowpop(sc, {**PC_PAGE, "gemrate": GemratePop(2, 2, 2, _rec(gems=2, total=2))}, today=date(2026, 9, 24))
    assert sc.pop_source == "gemrate" and sc.pop_psa10 == 2
    assert sc.pop_issue and "censo em formação" in sc.pop_issue
    assert sc.pts_scarcity == sc.pts_supply


def test_gemrate_set_com_3_meses_ou_mais_confia_no_censo():
    assert pop_trust_issue([0] * 9 + [359], 30.0, age_months=4, source="gemrate") is None
    assert "censo em formação" in pop_trust_issue([0] * 9 + [3], 30.0, age_months=2, source="gemrate")
    assert "censo em formação" in pop_trust_issue([0] * 9 + [2], None, age_months=0, source="gemrate")
