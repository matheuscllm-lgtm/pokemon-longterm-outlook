"""ASI-Evolve evaluator — fitness do score de longo prazo.

Contrato ASI-Evolve: recebe o caminho de um programa-candidato (a política de
pesos), avalia, e imprime no stdout `{"score": float, "metrics": {...}}`. O
'score' é o que o loop evolutivo maximiza: a correlação de posto (Spearman)
entre o total do score e a variação de preço REALIZADA (ground truth do
dataset.json).

Features (o que é fixo/curado) saem do pacote `outlook`; os PESOS (o que é
chutado/evolvível) saem do candidato. Roda de qualquer cwd: injeta a raiz do
repo no sys.path.
"""
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]                # raiz do repo (pra importar `outlook`)
sys.path.insert(0, str(ROOT))

from outlook.evaluate import MIN_N, spearman           # noqa: E402
from outlook.notorious import match_notorious, tier_points  # noqa: E402
from outlook.scoring import is_heavy_reprint           # noqa: E402

_TIER_LETTER = {25: "S", 18: "A", 12: "B"}             # tier_points -> letra


def features_of(row: dict) -> dict:
    """Extrai as features FIXAS de uma linha do dataset (curadoria + sinais)."""
    card, sm = row["card"], row["set_meta"]
    rel = date.fromisoformat(sm["releaseDate"].replace("/", "-"))
    today = date.today()
    age = (today.year - rel.year) * 12 + (today.month - rel.month)
    tier = _TIER_LETTER.get(tier_points(match_notorious(card.get("name", ""))))
    return {
        "rarity": card.get("rarity", "?"),
        "age_months": age,
        "market_usd": row["market_usd"],
        "appeal_tier": tier,
        "heavy_reprint": is_heavy_reprint(sm["id"], sm.get("name", "")),
        "alt_art": "alternate" in card.get("name", "").lower(),
    }


def _load(path: Path):
    spec = importlib.util.spec_from_file_location("candidate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    candidate_path = (Path(sys.argv[1]) if len(sys.argv) > 1
                      else HERE / "initial_program.py")
    dataset = json.loads((HERE / "dataset.json").read_text(encoding="utf-8"))
    candidate = _load(candidate_path)

    comps = {"Personagem": [], "Raridade": [], "Supply": [], "Preço": []}
    totals, trends = [], []
    for row in dataset:
        if row.get("trend_pct") is None:
            continue
        c = candidate.score_components(features_of(row))
        for k in comps:
            comps[k].append(c[k])
        totals.append(sum(c.values()))
        trends.append(row["trend_pct"])

    n = len(trends)
    fit = spearman(totals, trends) if n >= 2 else None
    payload = {
        "score": fit if fit is not None else 0.0,
        "metrics": {
            "n": n,
            "sufficient": bool(n >= MIN_N and fit is not None),
            **{f"spearman_{k}": (spearman(v, trends) if n >= 2 else None)
               for k, v in comps.items()},
        },
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
