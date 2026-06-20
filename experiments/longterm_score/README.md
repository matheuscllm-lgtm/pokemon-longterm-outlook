# Experimento ASI-Evolve — `longterm_score`

Monta o score de longo prazo como um experimento do
[ASI-Evolve](https://github.com/GAIR-NLP/ASI-Evolve): um loop que evolui um
programa pra maximizar o fitness de um avaliador. Aqui o "programa" são os
**pesos** do score, e o fitness mede se o score ordena as cartas como o mercado
de fato se moveu.

## Arquivos
| Arquivo | Papel |
|---|---|
| `input.md` | enunciado do problema (objetivo, o que pode/não pode mudar, **guardrail de horizonte**) |
| `initial_program.py` | a política EVOLVÍVEL — só os pesos/limiares. Reproduz o score do tool hoje (fidelidade testada). |
| `evaluator.py` | contrato ASI-Evolve: lê `dataset.json`, re-pontua com o candidato, imprime `{"score","metrics"}` |
| `eval.sh` | wrapper que o framework chama: `eval.sh <candidato>` |
| `config.yaml` | template de config (LLM via env var — **nunca comite chave**) |
| `dataset.json` | snapshot de ground truth: features + tendência realizada (CardMarket) por carta |

## Separação de responsabilidades
- **Evolui (palpite):** os números em `initial_program.py`.
- **Fixo (julgamento humano):** a curadoria personagem→tier (`outlook/notorious.py`)
  e a extração de features (`evaluator.py`).
- **Porta de volta:** quando um candidato vence de forma clara e estável, leve
  os números pra `outlook/scoring.py` (+ tiers em `notorious.py`). Este diretório
  é o laboratório; o pacote `outlook/` é a entrega.

## Rodar o baseline (sem LLM, da raiz do repo)
```bash
bash experiments/longterm_score/eval.sh
# -> {"score": <Spearman>, "metrics": {"n":..., "sufficient":..., ...}}
```

## Honestidade (importante)
O ground truth hoje é de **curto prazo** (CardMarket avg7 vs avg30). A
calibração mais recente deu fitness ~**−0.22** com N=143 — reversão à média, não
erro do score. **Não persiga este fitness cegamente** (viraria momentum). Veja o
guardrail completo no `input.md`. O loop só vale como otimizador de verdade
quando houver ground truth de horizonte longo.
