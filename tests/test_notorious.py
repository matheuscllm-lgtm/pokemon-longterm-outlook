"""Testes do matcher de notórios + tiers de apelo (Pokémon e treinadores).

Contratos referenciados no docstring de outlook/notorious.py.
"""
from outlook.notorious import (APPEAL_DEFAULT, A_POINTS, B_POINTS, NOTORIOUS,
                               POKEMON_A, POKEMON_B, POKEMON_S, S_POINTS,
                               TRAINER_A, TRAINER_S, appeal_points,
                               is_notorious, match_notorious, tier_points)


# ── Matcher: palavra inteira, sufixos, prefixos ──────────────────────────────
def test_match_whole_word_and_suffixes():
    assert match_notorious("Charizard ex") == "Charizard"
    assert match_notorious("Dark Charizard") == "Charizard"
    assert match_notorious("Mega Charizard EX") == "Charizard"
    # item Mega Stone NÃO é a carta do Pokémon
    assert match_notorious("Charizardite X") is None


def test_mew_does_not_match_inside_mewtwo():
    assert match_notorious("Mewtwo VSTAR") == "Mewtwo"
    assert match_notorious("Mew ex") == "Mew"


def test_non_notorious_and_empty():
    assert match_notorious("Tinkatuff") is None
    assert match_notorious("") is None
    assert match_notorious(None) is None
    assert not is_notorious("Tinkatuff")


# ── Treinadores: a lacuna que esta mudança fecha ─────────────────────────────
def test_trainers_now_match():
    assert match_notorious("Marnie") == "Marnie"
    assert match_notorious("Iono") == "Iono"
    assert match_notorious("Cynthia") == "Cynthia"
    assert is_notorious("Lillie")


def test_trainer_brand_carries_to_pokemon_card():
    # "Iono's Bellibolt ex": Bellibolt não é notório, mas a marca da treinadora
    # carrega o apelo -> casa Iono e herda o tier dela (S).
    assert match_notorious("Iono's Bellibolt ex") == "Iono"
    assert appeal_points("Iono's Bellibolt ex") == S_POINTS


def test_single_letter_N_token_only():
    # "N" só casa como token isolado — nunca dentro de outra palavra.
    assert match_notorious("N") == "N"
    assert match_notorious("N's Reshiram ex") == "N"  # Reshiram não é notório
    assert match_notorious("Snorlax") == "Snorlax"    # casa Snorlax, não "N"
    assert match_notorious("Nessa") == "Nessa"        # casa Nessa, não "N"
    assert match_notorious("Bianca") is None          # Bianca não está na lista


def test_higher_tier_wins_when_two_notorious_match():
    # Dois notórios na mesma carta -> vence o de MAIOR apelo (não o mais longo).
    assert match_notorious("N's Zoroark ex") == "N"          # N(S) > Zoroark(B)
    assert appeal_points("N's Zoroark ex") == S_POINTS
    assert match_notorious("Cynthia's Garchomp ex") == "Cynthia"  # S > B


# ── Tiers de apelo ───────────────────────────────────────────────────────────
def test_appeal_tiers_values():
    assert appeal_points("Charizard ex") == S_POINTS        # 25
    assert appeal_points("Marnie") == S_POINTS              # 25 (treinadora S)
    assert appeal_points("Sylveon ex") == A_POINTS          # 18
    assert appeal_points("Nessa") == A_POINTS               # 18 (treinadora A)
    assert appeal_points("Machamp ex") == B_POINTS          # 12
    assert appeal_points("Tinkatuff") == APPEAL_DEFAULT     # 8


def test_tier_ordering_is_strict():
    assert S_POINTS > A_POINTS > B_POINTS > APPEAL_DEFAULT


def test_tier_points_takes_matched_name():
    assert tier_points("Charizard") == S_POINTS
    assert tier_points("Sylveon") == A_POINTS
    assert tier_points("Machamp") == B_POINTS
    assert tier_points(None) == APPEAL_DEFAULT


def test_each_name_in_exactly_one_tier():
    groups = [POKEMON_S, POKEMON_A, POKEMON_B, TRAINER_S, TRAINER_A]
    allnames = [n for g in groups for n in g]
    assert len(allnames) == len(set(allnames))      # sem colisão entre tiers
    assert set(allnames) == set(NOTORIOUS)          # NOTORIOUS cobre tudo


# ── Casos herdados do test_notorious.py da main (antes dos tiers) ────────────
# A main tinha estes contratos e a versão com tiers não os cobria; ficam aqui
# pra fusão não perder cobertura.
def test_basic_forms_match_the_pokemon():
    assert match_notorious("Mega Lucario ex") == "Lucario"
    assert match_notorious("Gardevoir ex") == "Gardevoir"


def test_match_ignores_tcgplayer_number_suffix():
    # Mesmo com o ' - 181/132' que o tcgcsv às vezes traz, o nome casa.
    assert match_notorious("Mega Latias ex - 181/132") == "Latias"
    # A main esperava "Zoroark" aqui só porque N não existia na lista plana de
    # Pokémon. Com treinadores, vence o maior apelo (decisão 2026-09-24, issue
    # pendencias#9): quem puxa o preço de "N's Zoroark ex" é o N, não o Zoroark.
    assert match_notorious("N's Zoroark ex - 286/217") == "N"


def test_trainer_possessive_does_not_hijack_pokemon_when_trainer_unlisted():
    # "Team Rocket" não é treinador da lista (Giovanni é) -> casa o Pokémon.
    assert match_notorious("Team Rocket's Mewtwo ex") == "Mewtwo"


def test_hyphenated_name_matches():
    assert match_notorious("Ho-Oh ex") == "Ho-Oh"


def test_accents_in_surrounding_text_do_not_break_match():
    # O texto é normalizado (NFD) antes do match — acento adjacente não atrapalha.
    assert match_notorious("Pokémon Pikachu δ") == "Pikachu"


def test_modern_non_notorious_returns_none():
    assert match_notorious("Iron Valiant ex") is None


def test_is_notorious_is_boolean_wrapper():
    assert is_notorious("Pikachu") is True
    assert is_notorious("Tinkatuff") is False


# ── Treinadores de nome curto: sem falso positivo dentro de outra palavra ────
def test_short_trainer_names_do_not_match_inside_pokemon_names():
    # Bea/Rosa/Volo/Lillie são prefixos de Pokémon reais — o lookahead
    # (?![a-z]) tem que barrar, senão o Pokémon herdaria tier de treinador.
    assert match_notorious("Beautifly") is None
    assert match_notorious("Roserade") is None
    assert match_notorious("Volcarona") is None
    assert match_notorious("Lillipup") is None
