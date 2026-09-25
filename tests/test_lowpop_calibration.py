"""Calibração do modo low pop (outlook/lowpop_calibration.py) — funções puras
+ leitura dos artefatos do run (snapshot/cache) em diretório temporário."""
from __future__ import annotations

import csv
import json

from outlook import lowpop_calibration as cal
from outlook.scoring import DEMAND_SALES_BANDS, SCARCITY_POP10_BANDS


def test_quantile_interpola_como_numpy():
    xs = [1, 2, 3, 4]
    assert cal.quantile(xs, 0.5) == 2.5
    assert cal.quantile(xs, 0.0) == 1
    assert cal.quantile(xs, 1.0) == 4
    assert cal.quantile([7], 0.9) == 7


def test_nice_log_arredonda_para_numero_redondo_em_escala_log():
    assert cal.nice_log(287.4) == 300
    assert cal.nice_log(1100) == 1000
    assert cal.nice_log(1300) == 1500
    assert cal.nice_log(4.2) == 5
    assert cal.nice_log(0.87) == 1
    assert cal.nice_log(0.42) == 0.5
    assert cal.nice_log(0) == 0


def test_band_shares_le_cobre_o_pool_inteiro_e_nao_conta_duas_vezes():
    pop = [10, 50, 51, 500, 501, 2000, 2001, 5000, 5001, 10000, 10001]
    rows = cal.band_shares_le(pop, SCARCITY_POP10_BANDS, 3)
    assert [n for _, _, n in rows] == [2, 2, 2, 2, 2, 1]
    assert sum(n for _, _, n in rows) == len(pop)
    assert [p for _, p, _ in rows] == [25, 22, 18, 12, 7, 3]


def test_band_shares_ge_cobre_o_pool_inteiro():
    spm = [90, 60, 59.9, 30, 29.9, 5, 4.9, 2, 1.9]
    rows = cal.band_shares_ge(spm, DEMAND_SALES_BANDS, 3)
    assert [n for _, _, n in rows] == [2, 2, 2, 2, 1]
    assert [p for _, p, _ in rows] == [25, 20, 14, 8, 3]


def test_proposta_de_escassez_e_crescente_e_mantem_a_escada_de_pontos():
    # Pool concentrado: quantis quase iguais → o desempate força cortes crescentes.
    pop = [100] * 50 + [120] * 50
    bands = cal.propose_bands_le(pop, [25, 22, 18, 12, 7, 3])
    caps = [c for c, _ in bands]
    assert caps == sorted(caps) and len(set(caps)) == len(caps)
    assert [p for _, p in bands] == [25, 22, 18, 12, 7]


def test_proposta_de_demanda_e_decrescente_e_mantem_a_escada_de_pontos():
    spm = [0.5, 1, 2, 4, 8, 16, 32, 64]
    bands = cal.propose_bands_ge(spm, [25, 20, 14, 8, 3])
    floors = [c for c, _ in bands]
    assert floors == sorted(floors, reverse=True) and len(set(floors)) == len(floors)
    assert [p for _, p in bands] == [25, 20, 14, 8]


def _row(name, series, pop10, spm, pts_sc, pts_dm, char=25, rar=25, usd=100.0):
    return {"name": name, "number": "1", "set_name": "S", "series": series,
            "rarity": "R", "notorious": "", "market_usd": usd, "psa10_usd": usd,
            "spm": spm, "pop10": pop10, "pop_total": (pop10 or 0) * 3,
            "pts_character": char, "pts_rarity": rar,
            "pts_scarcity": pts_sc, "pts_demand": pts_dm}


def test_rescore_recalcula_so_o_que_foi_medido():
    pool = [_row("A", "SV", 40, 35.0, 25, 25),      # medida
            _row("B", "SV", None, None, 12, 20)]    # sem censo/vendas: mantém
    pool[0]["_trusted"], pool[1]["_trusted"] = True, False
    out = cal.rescore(pool, ((10, 25), (100, 18)), 3, ((50.0, 25), (5.0, 14)), 3)
    scores = {r["name"]: s for s, r in out}
    assert scores["A"] == 25 + 25 + 18 + 14   # 40 > 10 → 18; 35 < 50, ≥ 5 → 14
    assert scores["B"] == 25 + 25 + 12 + 20   # inalterado


def test_relatorio_sem_pool_avisa_em_vez_de_inventar():
    md = cal.build_report([], [])
    assert "Sem pool low pop" in md


def test_relatorio_traz_distribuicao_faixas_e_efeito_no_topo():
    pool = []
    for i in range(1, 41):
        pop10, spm = i * 30, 40 / i
        pool.append(_row(f"C{i}", "SV" if i % 2 else "XY", pop10, spm,
                         cal.scarcity_points(pop10), cal.demand_points(spm)))
    cache = [{"psa10_usd": 300.0, "raw_usd": 100.0, "spm": 2.0, "pop10": 100, "pop_total": 400}]
    md = cal.build_report(pool, cache, n_top=10)
    for needle in ("## Distribuição (quantis)", "## Por era (pool)", "| SV |", "| XY |",
                   "Faixas VIGENTES", "Faixas PROPOSTAS", "SCARCITY_POP10_BANDS = (",
                   "DEMAND_SALES_BANDS = (", "## Efeito no top 10", "Sobreposição",
                   "Prêmio PSA 10 ÷ crua", "Spearman pop10 × vendas/mês"):
        assert needle in md, needle


def test_load_pool_e_load_cache_leem_os_artefatos_do_run(tmp_path):
    snap = tmp_path / "snapshot_2026-09-21.csv"
    with snap.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "date", "source", "card_id", "set_id", "set_name", "number", "name", "rarity",
            "series", "release", "market_usd", "notorious", "heavy_reprint", "score",
            "pts_character", "pts_rarity", "pts_supply", "pts_price", "lowpop", "psa10_usd",
            "psa10_sales_per_month", "pop_psa10", "pop_total", "pts_scarcity", "pts_demand"])
        w.writeheader()
        base = {"date": "2026-09-21", "source": "tcgcsv", "card_id": "1", "set_id": "s",
                "set_name": "Set", "number": "1", "name": "Mew", "rarity": "SIR",
                "series": "SV", "release": "2024-01-01", "market_usd": "50.00",
                "notorious": "Mew", "heavy_reprint": "0", "score": "90",
                "pts_character": "25", "pts_rarity": "25", "pts_supply": "7", "pts_price": "20"}
        w.writerow({**base, "lowpop": "1", "psa10_usd": "150.00", "psa10_sales_per_month": "4.5",
                    "pop_psa10": "120", "pop_total": "400", "pts_scarcity": "22", "pts_demand": "14"})
        w.writerow({**base, "lowpop": "0", "psa10_usd": "", "psa10_sales_per_month": "",
                    "pop_psa10": "", "pop_total": "", "pts_scarcity": "", "pts_demand": ""})
    pool = cal.load_pool(snap)
    assert len(pool) == 1 and pool[0]["pop10"] == 120 and pool[0]["spm"] == 4.5

    cache = tmp_path / "pc"
    cache.mkdir()
    (cache / "a.json").write_text(json.dumps({"status": "ok", "usd": 900.0, "raw_usd": 300.0,
                                             "sales_per_month": 1.0, "pop_psa": [0] * 9 + [30]}))
    (cache / "b.json").write_text(json.dumps({"status": "sem preço PSA 10"}))
    (cache / "c.json").write_text("{corrompido")
    rows = cal.load_cache(cache)
    assert len(rows) == 1 and rows[0]["pop10"] == 30 and rows[0]["pop_total"] == 30


def test_parse_cuts_exige_um_corte_por_degrau():
    import pytest
    assert cal.parse_cuts("50,500,2000", [25, 22, 18]) == ((50.0, 25), (500.0, 22), (2000.0, 18))
    with pytest.raises(ValueError):
        cal.parse_cuts("50,500", [25, 22, 18])


def test_census_trusted_espelha_o_guard_do_scoring():
    assert cal.census_trusted(120, 400, 4.5) is True
    assert cal.census_trusted(1, 4, None) is False          # censo total < 25 (página fina)
    assert cal.census_trusted(2, 229, 4.3) is False         # vende mais do que existe
    assert cal.census_trusted(None, None, 4.3) is False     # pop n/d
    assert cal.census_trusted(40, 40, 30.0) is True         # tudo PSA 10, vendas ≤ pop


def test_propostas_continuam_monotonicas_com_quantis_zero():
    # Pool com maioria pop10 == 0 (vintage sem PSA 10): cortes não podem colapsar em 0,0,0…
    bands = cal.propose_bands_le([0] * 60 + [5000] * 5, [25, 22, 18, 12, 7, 3])
    caps = [c for c, _ in bands]
    assert caps == sorted(caps) and len(set(caps)) == len(caps)
    bands = cal.propose_bands_ge([0.0] * 60 + [30.0] * 5, [25, 20, 14, 8, 3])
    floors = [c for c, _ in bands]
    assert floors == sorted(floors, reverse=True) and len(set(floors)) == len(floors)


def test_relatorio_com_cortes_da_cli_e_zero_censo_confiavel_nao_quebra():
    pool = [_row("A", "SV", 1, 0.5, 25, 3)]
    pool[0]["pop_total"] = 2  # página fina → censo não confiável → sem topo a comparar
    sc = cal.parse_cuts("50,500,2000,5000,10000", [25, 22, 18, 12, 7])
    dm = cal.parse_cuts("60,30,5,2", [25, 20, 14, 8])
    md = cal.build_report(pool, [], n_top=5, proposed_sc=sc, proposed_dm=dm)
    assert "Nenhuma carta com censo confiável" in md


def test_census_trusted_respeita_a_fonte_gemrate():
    # Censo pequeno mas OFICIAL (GemRate) é escassez real, não página fina.
    assert cal.census_trusted(4, 9, None, "gemrate") is True
    assert cal.census_trusted(4, 9, None, "pricecharting") is False
    assert cal.census_trusted(0, 9, None, "gemrate") is False     # nenhuma PSA 10 ainda


def test_census_trusted_gemrate_set_com_menos_de_3_meses_e_censo_em_formacao():
    # Espelho do guard novo do scoring (2026-09-24, 2ª leitura): a GemRate já
    # publica o set, mas ninguém gradou ainda — "pop 2" é calendário.
    assert cal.census_trusted(2, 2, None, "gemrate", age_months=0) is False
    assert cal.census_trusted(3, 9, None, "gemrate", age_months=2) is False
    assert cal.census_trusted(359, 800, 30.0, "gemrate", age_months=4) is True


def test_load_pool_le_a_idade_do_set_e_o_topo_exclui_censo_em_formacao(tmp_path):
    from datetime import date as _d
    snap = tmp_path / "snapshot_2026-09-24.csv"
    hdr = ("date,source,card_id,set_id,set_name,number,name,rarity,series,release,market_usd,notorious,"
           "heavy_reprint,score,pts_character,pts_rarity,pts_supply,pts_price,lowpop,psa10_usd,"
           "psa10_sales_per_month,pop_psa10,pop_total,pts_scarcity,pts_demand,pop_source\n")
    novo = ("2026-09-24,tcgcsv,1,s1,ME: 30th Celebration,154,Gengar ex,Special Illustration Rare,Mega Evolution,"
            "2026-09-16,133.6,Gengar,0,71,25,21,25,0,1,,,2,2,25,0,gemrate\n")
    velho = ("2026-09-24,tcgcsv,2,s2,SWSH07: Evolving Skies,184,Sylveon V,Ultra Rare,Sword & Shield,"
             "2021-08-27,199.1,,0,60,15,15,7,0,1,399.57,30,7163,13906,7,20,gemrate\n")
    snap.write_text(hdr + novo + velho, encoding="utf-8")
    pool = cal.load_pool(snap)
    assert {r["name"]: r["age_months"] for r in pool} == {"Gengar ex": 0, "Sylveon V": 61}
    md = cal.build_report(pool, [], n_top=5)
    assert "censo confiável: **1**" in md
    assert "Gengar ex" not in md.split("## Efeito no top")[1]


# ── Candidatos de calibração (2026-09-25): só análise, nada muda no score ────

def test_pontos_relativos_a_mediana_da_era_escassez():
    # pop10 ÷ mediana da era em degraus de ÷2: ≤¼ 25 · ≤½ 22 · ≤1× 18 · ≤2× 12 · ≤4× 7 · resto 3
    med = 1000.0
    assert cal.relative_scarcity_points(250, med) == 25
    assert cal.relative_scarcity_points(251, med) == 22
    assert cal.relative_scarcity_points(1000, med) == 18
    assert cal.relative_scarcity_points(2000, med) == 12
    assert cal.relative_scarcity_points(4000, med) == 7
    assert cal.relative_scarcity_points(4001, med) == 3
    assert cal.relative_scarcity_points(0, med) == 25


def test_pontos_relativos_a_mediana_da_era_demanda_em_log():
    # vendas/mês ÷ mediana da era em degraus de ×2: ≥4× 25 · ≥2× 20 · ≥1× 14 · ≥½ 8 · resto 3
    med = 8.0
    assert cal.relative_demand_points(32.0, med) == 25
    assert cal.relative_demand_points(16.0, med) == 20
    assert cal.relative_demand_points(8.0, med) == 14
    assert cal.relative_demand_points(4.0, med) == 8
    assert cal.relative_demand_points(3.9, med) == 3
    assert cal.relative_demand_points(0.0, med) == 3


def test_mediana_por_era_cai_na_global_quando_a_era_e_pequena():
    pool = [_row(f"S{i}", "SV", 1000 * (i + 1), 10.0 * (i + 1), 3, 3) for i in range(6)]
    pool += [_row("E1", "EX", 10, 0.5, 25, 3), _row("E2", "EX", 20, 1.0, 25, 3)]
    for r in pool:
        r["_trusted"] = True
    meds = cal.era_medians(pool, "pop10", min_n=5)
    assert meds["SV"] == 3500          # mediana de 1000..6000
    assert "EX" not in meds            # 2 cartas < 5 → sem mediana própria
    g = cal.global_median(pool, "pop10")
    assert g == cal.quantile([1000, 2000, 3000, 4000, 5000, 6000, 10, 20], 0.5)


def test_candidato_gate_exclui_quem_vende_menos_de_2_por_mes_e_tira_a_demanda_do_score():
    pool = [_row("Liquida", "SV", 100, 30.0, 22, 20),
            _row("Parada", "SV", 10, 1.0, 25, 3),
            _row("SemVenda", "SV", 10, None, 25, 3)]
    for r in pool:
        r["_trusted"] = True
    ranked, gated = cal.rescore_candidate(pool, "gate")
    assert [r["name"] for _, r in ranked] == ["Liquida"]
    assert sorted(r["name"] for r in gated) == ["Parada", "SemVenda"]
    assert ranked[0][0] == 25 + 25 + 22     # sem Demanda: máximo 75


def test_candidato_escassez_relativa_premia_o_raro_da_propria_era():
    # Vintage: pop 40 é o normal da era (18); moderno: pop 4000 é o normal da era (18).
    pool = [_row(f"V{i}", "WotC", 40, 1.0, 22, 3) for i in range(5)]
    pool += [_row(f"M{i}", "SV", 4000, 30.0, 12, 20) for i in range(5)]
    pool += [_row("Vraro", "WotC", 5, 1.0, 25, 3), _row("Mraro", "SV", 500, 30.0, 22, 20)]
    for r in pool:
        r["_trusted"] = True
    ranked, gated = cal.rescore_candidate(pool, "scarcity_era")
    pts = {r["name"]: s - r["pts_character"] - r["pts_rarity"] - r["pts_demand"] for s, r in ranked}
    assert pts["Vraro"] == 25 and pts["Mraro"] == 25
    assert pts["V0"] == 18 and pts["M0"] == 18
    assert gated == []


def test_candidato_demanda_por_era_mantem_escassez_vigente():
    pool = [_row(f"V{i}", "WotC", 40, 1.0, 22, 3) for i in range(5)]
    pool += [_row("Vquente", "WotC", 40, 4.3, 22, 8)]
    for r in pool:
        r["_trusted"] = True
    ranked, _ = cal.rescore_candidate(pool, "demand_era")
    pts = {r["name"]: s - r["pts_character"] - r["pts_rarity"] - 22 for s, r in ranked}
    assert pts["Vquente"] == 25           # 4,3 ÷ 1 ≥ 4× a mediana da era
    assert pts["V0"] == 14                # = mediana


def test_relatorio_de_candidatos_traz_entra_sai_e_spearman_por_candidato():
    pool = []
    for i in range(1, 41):
        pop10, spm = i * 30, 40 / i
        pool.append(_row(f"C{i}", "SV" if i % 2 else "XY", pop10, spm,
                         cal.scarcity_points(pop10), cal.demand_points(spm)))
    md = cal.candidates_report(pool, n_top=10)
    for needle in ("# Candidatos de calibração", "## Vigente",
                   "## A. Demanda em log por era", "## B. Escassez relativa à era",
                   "## C. Gate ≥2 vendas/mês", "Sobreposição com o top 10 vigente",
                   "**Entra**", "**Sai**", "Spearman Escassez × Demanda (pontos)",
                   "| # | Carta | Era | pop10 | vendas/mês | Esc | Dem | score vigente → candidato |"):
        assert needle in md, needle
    assert "não disputa" in md            # gate reporta quantas cartas ficaram de fora


def test_relatorio_de_candidatos_sem_censo_confiavel_avisa():
    pool = [_row("A", "SV", 1, 0.5, 25, 3)]
    pool[0]["pop_total"] = 2
    md = cal.candidates_report(pool, n_top=5)
    assert "Nenhuma carta com censo confiável" in md


def test_tabela_de_medianas_avisa_fallback_global_em_cada_coluna():
    # 6 cartas com censo (sem aviso no pop) mas só 2 com vendas → a coluna de
    # vendas tem que avisar "usa global", igual ao que rescore_candidate faz.
    pool = [_row(f"S{i}", "SV", 1000, None, 18, 3) for i in range(4)]
    pool += [_row("S4", "SV", 1000, 30.0, 18, 20), _row("S5", "SV", 1000, 30.0, 18, 20)]
    md = cal.candidates_report(pool, n_top=5)
    linha = next(l for l in md.splitlines() if l.startswith("| SV |"))
    assert linha == "| SV | 6 | 1000 | 2 (<5: usa global) | 30 |"
