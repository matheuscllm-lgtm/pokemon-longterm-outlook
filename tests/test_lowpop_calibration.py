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
