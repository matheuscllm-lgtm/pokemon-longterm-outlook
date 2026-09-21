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
    pop = [10, 50, 51, 200, 201, 500, 501, 2000, 2001, 10000, 10001]
    rows = cal.band_shares_le(pop, SCARCITY_POP10_BANDS, 3)
    assert [n for _, _, n in rows] == [2, 2, 2, 2, 2, 1]
    assert sum(n for _, _, n in rows) == len(pop)
    assert [p for _, p, _ in rows] == [25, 22, 18, 12, 7, 3]


def test_band_shares_ge_cobre_o_pool_inteiro():
    spm = [40, 30, 29.9, 10, 9.9, 3, 2.9, 1, 0.5]
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
