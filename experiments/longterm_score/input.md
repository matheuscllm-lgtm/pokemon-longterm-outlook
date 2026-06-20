# Experimento: calibrar o score de longo prazo (Pokémon TCG)

## Objetivo
Evoluir `initial_program.py` (a política de PESOS do score) buscando o melhor
fitness no `evaluator.py`: a correlação de posto (Spearman) entre o score e a
variação de preço REALIZADA das cartas (ground truth em `dataset.json`).

## O que pode mudar (só os palpites numéricos)
- pontos por tier de apelo (S/A/B/fora);
- pontos por faixa de raridade;
- limiares de supply (meses → pontos) e o teto de reprint;
- faixas de preço → pontos;
- como os 4 componentes somam (ex.: pesos relativos).

## O que NÃO pode mudar (é entrega, não palpite)
- A curadoria personagem→tier (vive em `outlook/notorious.py`).
- A extração de features (vive no `evaluator.py`).
- A natureza do tool: heurística TRANSPARENTE 0-100, 4 componentes 0-25. Nada
  de hardcode por carta, nada de modelo opaco, nada de inventar preço.

## Fitness
`{"score": Spearman(total, realizado), "metrics": {...por componente...}}`,
onde "realizado" = tendência CardMarket avg7 vs avg30 (em `dataset.json`).

## ⚠️ GUARDRAIL DE HORIZONTE — leia antes de evoluir
Achado da calibração (2026-06-20, N=143): o ground truth é de **curto prazo**
(semana vs mês) e o score é de **longo prazo**. Na medição atual o fitness é
levemente **negativo** (~−0.22), o que é compatível com **reversão à média**
(blue-chips consolidando enquanto cartas especulativas dão pico recente) — não
é erro do score.

Logo: **NÃO maximize cegamente este fitness.** Otimizar a ordenação de curto
prazo viraria o score num caçador de momentum — o OPOSTO do objetivo de longo
prazo. Use o fitness como **diagnóstico** (procure sinal forte, |Spearman| ≥
0.30, e estável entre runs), não como alvo a perseguir. O alvo honesto só fica
mensurável com um ground truth de **horizonte longo** (ex.: variação 6-12 meses)
— quando existir, troque o `dataset.json` e o fitness passa a valer como alvo.

## Rodar
```bash
# 1) gerar/atualizar o ground truth (da raiz do repo):
python run_evaluate.py --eras "Scarlet & Violet" --max-sets 6 \
  --dump experiments/longterm_score/dataset.json
# 2) baseline do candidato atual:
bash experiments/longterm_score/eval.sh experiments/longterm_score/initial_program.py
# 3) loop evolutivo (no repo do ASI-Evolve, com chave de LLM configurada):
python main.py --experiment longterm_score --steps 40 --sample-n 3 \
  --eval-script /caminho/experiments/longterm_score/eval.sh
```
