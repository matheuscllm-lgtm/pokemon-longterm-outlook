#!/usr/bin/env bash
# ASI-Evolve chama: eval.sh <caminho-do-candidato>
# Emite no stdout o JSON {"score": float, "metrics": {...}} do evaluator.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$DIR/evaluator.py" "$@"
