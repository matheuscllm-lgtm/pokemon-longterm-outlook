# Pokémon Long-Term Outlook — cenário + score de longo prazo

> **O que é isto, em uma frase:** uma ferramenta que olha o catálogo atual de
> Pokémon TCG (preços de hoje no TCGPlayer), monta um panorama do mercado por
> era, e dá uma **nota 0-100 de potencial de longo prazo** pra cada carta
> premium — pra você saber **o que olhar primeiro**, não o que comprar.

⚠️ **Diferença pros scanners de arbitragem** (MYP/CT/COMC/Liga): aqueles
procuram carta **barata agora** (margem imediata entre lojas). Este avalia
**características de valorização futura** (demanda do personagem, raridade,
oferta encolhendo, patamar de preço). São perguntas diferentes.

## Glossário rápido

- **Score / heurística**: uma nota calculada por regras fixas e transparentes
  (não é inteligência artificial nem previsão — é uma régua de triagem).
- **Supply (oferta)**: quantas cópias existem/continuam sendo impressas. Set
  "fora de impressão" (out of print) = a oferta para de crescer; com demanda
  constante, o preço tende a subir.
- **Reprint**: reimpressão. Sets tipo *151* e *Prismatic Evolutions* são
  reimpressos por anos — a oferta NÃO encolhe, e o score reflete isso.
- **Alt art / SIR**: Special Illustration Rare — as artes alternativas que
  historicamente mais valorizam no moderno.
- **Market price**: o preço de referência do TCGPlayer (média de vendas reais).

## Como rodar

```powershell
cd C:\Users\mathe\pokemon-longterm-outlook
.venv\Scripts\python.exe run_outlook.py                # SV + SWSH + ME, top 50
.venv\Scripts\python.exe run_outlook.py --trend        # + setas de tendência (lento)
.venv\Scripts\python.exe run_outlook.py --top 30 --min-price 20
```

Precisa da `POKEMONTCG_API_KEY` (User env var — já está configurada nesta
máquina; key grátis em dev.pokemontcg.io). Sem a key roda também, só mais
devagar/limitado.

A entrega é a **tabela markdown no terminal/chat** (regra do operador:
resultado = tabela no chat, nunca arquivo por padrão). O `.md` em `outputs/`
é apoio local.

## Como o score funciona (0-100 = soma de 4 componentes 0-25)

| Componente | O que mede | Como pontua |
|---|---|---|
| **Personagem** | apelo perene do personagem (Pokémon **ou treinador**) | tier curado de apelo: **S** (ícone de liquidez: Charizard, Umbreon, Pikachu...) = 25 · **A** (fan-favorite forte) = 18 · **B** (segunda onda) = 12 · fora da lista = 8. Inclui **treinadores** (Marnie, Lillie, Cynthia, Iono, Acerola, N...) — SIR/full-art de treinadora valoriza tanto quanto de Pokémon e antes caía em 8 |
| **Raridade** | tier colecionável | SIR/alt-art 25 · IR 20 · TG/Character 16 · gold/secret/shiny 14 · ultra/VMAX 12 · resto ≤10 |
| **Supply** | oferta encolhendo | ≥36 meses = 25 · 24-36m = 22 · 18-24m = 18 · 12-18m = 12 · 6-12m = 7 · <6m = 3; set com **reprint forte** trava em 12 |
| **Preço** | espaço pra crescer com liquidez | $40-120 = 25 · $15-40 = 20 · >$300 = 12 (já precificado) · <$5 = 5 (sem liquidez) |

A tabela mostra os 4 componentes POR LINHA — você vê exatamente de onde a
nota veio e pode discordar de qualquer parcela.

## Limitações honestas (leia antes de usar)

1. **Não é previsão.** É triagem por características historicamente
   associadas a valorização. Mercado pode fazer outra coisa.
2. **Sem série histórica de preço.** A "tendência" opcional (`--trend`) vem
   de ~6 vendas públicas do PriceCharting — amostra minúscula, indício apenas.
3. **Era SWSH**: a API não distingue alt-art de ultra/secret comum pela
   raridade — alt arts SWSH (ex.: Moonbreon) ficam **subpontuadas** no
   componente raridade. A linha ganha nota explicando isso.
4. **Preço do dia.** O run reflete o market price de hoje; rode de novo
   quando quiser o retrato atualizado.
5. **Quem decide capital é o operador.** Score alto = "olhe primeiro".
   Não existe coluna "COMPRAR" de propósito.

## Avaliação e calibração — fechando o loop (ASI-Evolve)

O score sempre foi uma heurística de pesos curados à mão. Pra falar em
"precisão" é preciso uma **função de fitness**: medir se o score ordena as
cartas como o mercado de fato se moveu. É o que `outlook/evaluate.py` faz — e o
que o ASI-Evolve maximizaria.

- **Ground truth honesto:** tendência realizada do **CardMarket** (`avg7` vs
  `avg30`) lida direto da pokemontcg.io — por carta, sem scraping. É curto
  prazo (não prova valorização de longo prazo); mede a **consistência da
  ordenação**, não verdade.
- **Métrica:** correlação de posto (**Spearman**) entre o score (e cada
  componente) e a variação realizada. O tool é um ranking → posto importa mais
  que preço absoluto.
- **Rodar:** `python run_evaluate.py --eras "Scarlet & Violet" --max-sets 6`
  (entrega = tabela no chat). `--dump experiments/longterm_score/dataset.json`
  grava o dataset do experimento.
- **Guardrail:** abaixo de N=10 cartas com tendência válida, o relatório
  **recusa recalibrar** (amostra insuficiente — não fitar ruído).
- **Experimento ASI-Evolve:** `experiments/longterm_score/` traz o evaluator no
  contrato do framework (`{"score","metrics"}`), a política **evolvível**
  (`initial_program.py` = só os pesos) e o dataset. Regra: evoluir os PESOS,
  manter FIXA a curadoria humana (tiers em `notorious.py`); ganhos portam de
  volta pro `scoring.py`.
- ⚠️ `pricecharting.py` (o `--trend` do run principal) ficou **sem dados**: o
  PriceCharting passou a renderizar as vendas via JS. Use a calibração acima.

## Arquitetura

```
run_outlook.py           CLI: baixa catálogo → score → cenário + ranking
run_evaluate.py          CLI: calibração — score × tendência realizada (CardMarket)
outlook/ptcg_api.py      cliente pokemontcg.io (preços TCGPlayer + tendência CardMarket)
outlook/scoring.py       os 4 componentes do score + lista de sets com reprint forte
outlook/notorious.py     personagens notórios em tiers de apelo S/A/B (Pokémon + treinadores)
outlook/evaluate.py      avaliador/fitness (Spearman score×realizado) + relatório
outlook/pricecharting.py tendência best-effort (DESATUALIZADO — HTML virou JS)
outlook/report.py        cenário por era + tabela top-N em markdown
experiments/longterm_score/  experimento ASI-Evolve (evaluator, initial_program, dataset)
tests/                   testes dos componentes do score + do avaliador
```

Rodar os testes:

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```
