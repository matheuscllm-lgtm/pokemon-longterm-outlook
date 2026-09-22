<!-- FLEET:ESTILO-RESPOSTA v1 (2026-09-14) — cópia-mestra: scanners-commons/08-ESTILO-RESPOSTA.md. Editar LÁ e replicar; não divergir nesta cópia. -->
> **Estilo de resposta obrigatório (operador, 2026-09-14): CONCISO — teto de 200 palavras.**
> Toda resposta no chat, nesta ordem: **1) Objetivo** — 1 linha do que foi pedido · **2) O que foi feito** — bullets curtos, cada um com o *porquê* da decisão · **3) Dependências/pendências** — o que falta, o que bloqueia, de quem depende (`nenhuma` quando não houver).
> O teto conta **só prosa**. **Fora do teto** (nunca resumir, cortar nem "amostrar" pra caber): a tabela de entrega gerada pela ferramenta do repo (colada VERBATIM), blocos de comando/código, saída de teste colada como prova e artefato canônico do repo (brief, relatório, análise).
> Sem preâmbulo, sem repetir o pedido, sem recapitular o que já foi dito. Não cabe em 200 palavras? Entregue o essencial dentro do teto e ofereça o detalhe ("quer o detalhe de X?") — nunca estoure em silêncio.

# CLAUDE.md — pokemon-longterm-outlook

> **O que é isto, em uma frase:** uma ferramenta que olha o catálogo atual de
> Pokémon TCG (preços de hoje no TCGPlayer), monta um panorama do mercado por
> era, e dá uma **nota 0-100 de potencial de longo prazo** pra cada carta
> premium — pra você saber **o que olhar primeiro**, não o que comprar.

⚠️ **Diferença pros scanners de arbitragem** (MYP/CT/COMC/Liga): aqueles
procuram carta **barata agora** (margem imediata entre lojas). Este avalia
**características de valorização futura** (demanda do personagem, raridade,
oferta encolhendo, patamar de preço). São perguntas diferentes.

## 🛰️ Convenções herdadas da frota

> **Manual completo da frota** (repo público):
> https://github.com/matheuscllm-lgtm/scanners-commons — cópia-mestra local
> (PC do operador): `C:\Users\mathe\scanners-commons\`.

Este repo **não é scanner de arbitragem**, então **NÃO se aplicam aqui**:
margem bruta 30%, NM-only e o piso de relevância R$50 (~US$10). Não há
compra/venda — é triagem de longo prazo. O que **SE aplica**:

- **Entrega = tabela markdown no terminal/chat** (regra do operador:
  resultado = tabela no chat, **nunca arquivo por padrão**), gerada pela
  ferramenta do repo — nunca montada à mão. O `.md` em `outputs/` é apoio
  local; anexar arquivo **só sob pedido explícito** do operador.
- **Nunca inventar preço/dado** — fonte falhou → `n/d` honesto e segue;
  jamais fabrica número (vale pra tendência, coluna DH e disponibilidade).
- **Nunca recomendar compra** — score alto = "olhe primeiro". Quem decide
  capital é o operador; não existe coluna "COMPRAR" de propósito.

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

**Setup (1ª vez, qualquer máquina):**

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt   # requests, pytest, py7zr
```

`py7zr` é opcional em runtime (lê os dumps `.ppmd.7z` do histórico de preço;
sem ele a tendência cai pra `n/d` honestamente, sem quebrar o run) — mas
recomendado.

**Dia a dia (PC do operador, PowerShell):**

```powershell
cd C:\Users\mathe\pokemon-longterm-outlook
.venv\Scripts\python.exe run_outlook.py                # SV + SWSH + ME, top 50
.venv\Scripts\python.exe run_outlook.py --trend        # + tendência REAL (histórico tcgcsv)
.venv\Scripts\python.exe run_outlook.py --top 30 --min-price 20
.venv\Scripts\python.exe run_outlook.py --sealed       # + ranking de selados (ETB/Box/Bundle/Tin)
.venv\Scripts\python.exe run_outlook.py --doubleholo dh.json  # + coluna DH (2ª opinião Double Holo)
.venv\Scripts\python.exe run_outlook.py --graded      # régua de PSA 10 (quem só compra graduada)
.venv\Scripts\python.exe run_outlook.py --lowpop --eras all --max-price 600 --graded-pool 300  # RÉGUA VIGENTE (2026-09-21): escassez + demanda medidas
.venv\Scripts\python.exe run_availability.py --top 100 # ONDE cada carta do top está mais barata em NM inglês
.venv\Scripts\python.exe -m outlook.history            # resumo da série histórica (maiores altas/quedas)
.venv\Scripts\python.exe -m outlook.validate           # calibração do score + backtest (quando houver história)
.venv\Scripts\python.exe -m outlook.lowpop_calibration # distribuição pop/vendas do último run --lowpop + fatia por faixa (calibrar faixas com dado)
```

Na nuvem/Linux, os mesmos comandos com `python3` (ou `.venv/bin/python`), ex.:
`python3 run_outlook.py --trend`.

**Defaults do CLI (`run_outlook.py`)**: `--top 50` · `--min-price 5.0` ·
`--max-price 1000.0` · `--eras` default = `Scarlet & Violet`, `Sword & Shield`,
`Mega Evolution` (`DEFAULT_ERAS`) · `--source {tcgcsv,ptcg}` default `tcgcsv` ·
`--trend-source {tcgcsv,pricecharting}` default `tcgcsv` · `--no-snapshot`
pula o snapshot diário.

**`run_availability.py`**: onde cada carta do top-N está mais barata em NM
inglês — CardTrader ao vivo (exige `CT_JWT`: env var ou `.env` do
card-trader-scanner) + referência/low TCGPlayer + links das demais
plataformas. Detalhes na seção "Onde está mais barata em NM inglês" abaixo.

**Tendência (`--trend`)**: usa **histórico de preço REAL** do tcgcsv.com
(dumps diários do TCGPlayer desde 2024-02-08), casado por `productId` — a
variação entre hoje e o ponto mais distante disponível (até 1 ano). É a fonte
default da tendência (`--trend-source tcgcsv`); a antiga raspagem do
PriceCharting segue acessível em `--trend-source pricecharting` (indício
fraco, ~6 vendas). O histórico exige `--source tcgcsv` (o casamento é por
productId) e o pacote `py7zr` (lê o `.7z` PPMd); sem ele a tendência cai pra
`n/d` honestamente, sem quebrar o run. Os dumps ficam em cache em
`data/cache/tcgcsv_history/` (1ª vez ~9s/ponto; depois instantâneo). Ressalvas
de interpretação: seção "Limitações honestas", item 2.

Além disso, cada run salva um **snapshot diário do score** em `data/snapshots/`
(use `--no-snapshot` para pular) — a memória própria da ferramenta, que alimenta
a validação/backtest longitudinal (`outlook/validate.py`).

`POKEMONTCG_API_KEY` (key grátis em dev.pokemontcg.io; no PC do operador já
está configurada como User env var) acelera a fonte alternativa
`--source ptcg`. Sem a key roda também, só mais devagar/limitado.

A entrega é a **tabela markdown no terminal/chat** (ver "Convenções herdadas
da frota" acima). O `.md` em `outputs/` é apoio local.

## Como o score funciona (0-100 = soma de 4 componentes 0-25)

| Componente | O que mede | Como pontua |
|---|---|---|
| **Personagem** | demanda perene do Pokémon | notório (lista curada de 60: Charizard, Umbreon, Pikachu...) = 25; resto = 8 |
| **Raridade** | tier colecionável | SIR/alt-art 25 · IR 20 · TG/Character/**Mega Attack** 16 · gold/secret/shiny/**Mega Hyper** 14 · ultra/VMAX 12 · ACE SPEC 10 · double rare/Rare Holo V 6 · resto 3 |
| **Supply** | oferta encolhendo | ≥36 meses = 25 · 24-36m = 22 · 18-24m = 18 · 12-18m = 12 · 6-12m = 7 · <6m = 3; set com **reprint forte** trava em 12 |
| **Preço** | espaço pra crescer com liquidez | $40-120 = 25 · $15-40 = 20 · $120-300 = 18 · $5-15 = 12 · >$300 = 12 (já precificado) · <$5 = 5 (sem liquidez) |

**Modo graded (`--graded`), para quem só compra PSA 10:** o componente **Preço**
deixa de ser medido no preço de carta crua e passa a ser medido no **slab PSA
10** — que é o mercado de quem compra graduada. Faixas: `$120-360 = 25` ·
`$45-120 = 20` · `$360-900 = 18` · `$15-45 = 12` · `>$900 = 12` · `<$15 = 5`.
São as MESMAS faixas raw multiplicadas por **3**, fator calibrado no múltiplo
PSA 10/raw observado no próprio top 25 (mediana 3.3×, p25 2.5×, p75 5.4×,
n=25) — reancoragem, não fórmula nova. Os outros 3 componentes não mudam, e o
score segue 4×25=100.

Entra também a **liquidez do slab** (vendas/mês do PSA 10): abaixo de **3/mês**
(fronteira B/C da régua de liquidez da frota) o componente é **tetado em 12** —
preço de tabela num mercado que quase não negocia não é preço realizável. Sem
dado de liquidez **não teta** (ausência não é sinal de iliquidez).

Preço e liquidez vêm de `outlook/psa10.py` (PriceCharting, a mesma fonte que
este repo já usa pra tendência — campo novo da mesma página). O modo consulta
só o **pool do topo** (`--graded-pool`, default 2× `--top`, mínimo 50): o
ranking raw define quem vale consultar, e só então o Preço é remedido. Carta
sem PSA 10 confiável **mantém a régua raw com o motivo declarado na linha** —
nunca zeramos nem inventamos. A tabela ganha as colunas `PSA 10 US$`,
`Vendas/mês` e `Raw US$` (esta só como contexto).

**Modo low pop (`--lowpop`) — a régua vigente (decisão do operador,
2026-09-21):** o objetivo é achar slabs PSA 10 com potencial de virar chase, e
a régua acima tinha dois componentes **cegos** pra isso: Supply mede idade do
set (não quantas cópias existem) e Preço mede faixa (não se alguém compra).
Neste modo os dois dão lugar a componentes **medidos** na MESMA página do
PriceCharting que o modo graded já lê (aba *POP Report* + vendas por nota,
provado em sonda de 30 cartas em 2026-09-21: 29/30 com censo, sem navegador):

| Componente | O que mede | Como pontua (faixas CALIBRADAS em 2026-09-21 — ver "Calibração das faixas" abaixo) |
|---|---|---|
| **Escassez** (substitui Supply) | nº de **PSA 10** no censo PSA | ≤50 = 25 · ≤500 = 22 · ≤2.000 = 18 · ≤5.000 = 12 · ≤10.000 = 7 · acima = 3 |
| **Demanda** (substitui Preço) | **vendas/mês** da PSA 10 | ≥60 (2+/dia) = 25 · ≥30 (1/dia) = 20 · ≥5 (1-3/semana) = 14 · ≥2 = 8 · abaixo = 3 |

Personagem e Raridade não mudam; o score segue 4×25 = 100. Regras duras:

- **Guard de página fina/duplicada** (achado da sonda: o PriceCharting tem
  páginas com censo quase vazio — Venusaur 15 com pop 4, Gardevoir ex 233 com
  pop 2). Pop baixa ALI é página errada, não escassez. Censo total <
  `POP_TOTAL_MIN_TRUST` (25), ou **mais vendas/mês de PSA 10 do que PSA 10
  existentes**, = "pop não confiável": Escassez cai pra idade do set, com o
  motivo na linha. Sem vendas publicadas, Demanda cai pra faixa de preço do
  slab, com nota. Nunca zera, nunca inventa.
- **`--max-price` vale sobre o PSA 10** (o operador pediu "tabela até
  US$600" = slab até 600); a crua só passa pelo piso `--min-price`.
- **Só o pool consultado entra no ranking** (misturar cartas medidas com
  cartas na régua antiga seria comparar réguas diferentes); o run declara
  quantas ficaram fora. O pool é montado em **rodízio por era**
  (`scoring.lowpop_pool`: melhores por Personagem + Raridade de cada era, em
  revezamento — o score cru é cego a era e sairia 100% SV) e **preenchido até
  ter `--graded-pool` cartas dentro do teto** (o PSA 10 só se conhece após a
  consulta; orçamento = 3× o pool). `--graded-pool` grande + **cache em
  disco** (`data/cache/pricecharting/`, 1 dia, gitignored) tornam o universo
  inteiro viável em runs repetidos (~3 s por carta nova).
- **Vintage entra**: `--eras vintage` (Wizards of the Coast, EX, Diamond &
  Pearl, HeartGold & SoulSilver, Black & White, XY, Sun & Moon — mapa
  explícito por nome em `outlook/tcgcsv_api.py::VINTAGE_SETS`, sem kits/POP/
  decks) e `--eras all`. No PriceCharting, 1st Edition/Shadowless são páginas
  separadas; a sem qualificador (unlimited) é a que o scanner escolhe.
- Colunas novas na tabela: `Pop PSA10 / total (gem)` e `Prêmio` (PSA 10 ÷
  crua — informativo, **não entra no score** até calibrar; < 1,5× vira nota).
  O `tcg_product_id` lido da página é a chave de join com o catálogo tcgcsv.
- O censo é **mensal**; velocidade de pop exige duas leituras — os campos vão
  no snapshot diário (`history.py`) justamente pra isso.

**Calibração das faixas (2026-09-21, com dado — nunca de cabeça):** run
canônico `--lowpop --eras all --max-price 600 --graded-pool 300` = 720
consultas ao PriceCharting (698 com preço PSA 10, 665 com censo), **300 slabs
dentro do teto** no ranking, **224 com censo confiável** (76 no balde "sem
censo": 40 páginas finas com censo total < 25, 33 sem censo, 3 vendendo mais
do que existem). `python -m outlook.lowpop_calibration` reproduz tudo abaixo
sobre qualquer run (`--scarcity`/`--demand` avaliam cortes candidatos).

| Métrica (pool no teto) | n | p5 | p10 | p25 | p50 | p75 | p90 | p95 |
|---|---|---|---|---|---|---|---|---|
| Pop PSA 10 (censo confiável) | 224 | 4 | 8 | 346 | 2.068 | 5.863 | 10.667 | 13.648 |
| Vendas/mês PSA 10 | 252 | 0,2 | 0,3 | 4,3 | 13 | 30 | 60 | 60 |
| Prêmio PSA 10 ÷ crua (todas as 698 consultas) | 693 | 2,3 | 2,8 | 5,4 | 16,6 | 46,6 | 116 | 193 |

- **Pop é bimodal**: um bloco vintage com 4-8 PSA 10 (ninguém grada: BW/HGSS/
  DP, medianas de 0,1-0,3 vendas/mês) e o bloco moderno de 1.000-14.000. Nas
  faixas provisórias, 50-200 tinha **3%** do pool e 2.000-10.000 concentrava
  **39%** num único degrau. Faixas calibradas → 17% · 11% · 21% · 21% · 18% ·
  11% (≤50 / ≤500 / ≤2.000 / ≤5.000 / ≤10.000 / acima).
- **Vendas/mês são discretas** (o PriceCharting escreve "N sales per
  day/week/month/year": 1/dia = 30, 1/semana = 4,3, 1/ano = 0,1). A faixa
  provisória ≥30 juntava **45%** do pool no topo. Cortes calibrados ficam
  ENTRE níveis: ≥60 (2+/dia) 12% · 30 (1/dia) 33% · 5-29 (1-3/semana) 21% ·
  2-4 16% · <2 19%.
- **Efeito no top 30** (só cartas com censo confiável): sobreposição 25/30;
  quem tem 6.000+ PSA 10 vendendo 1/dia desce de 82 pra 77 e quem tem ~1.000
  PSA 10 vendendo 2-3/dia sobe de 87 pra 93 (era: SWSH 13→10, ME 8→9, BW 0→2).
  A escada de pontos não mudou — só os cortes.
- ⚠️ **Achado estrutural, decisão do operador:** Spearman pop10 × vendas/mês
  = **+0,81** (n=220). Quem tem mais slabs vende mais, então os dois
  componentes somados se anulam em parte e o score premia o MEIO (pop ~1.000
  com 60-90 vendas/mês), não "poucas PSA 10 + demanda". Alternativa a decidir:
  Demanda como **giro** (vendas/mês ÷ pop de PSA 10 — que fração do que existe
  troca de mão por mês) em vez de vendas absolutas. Não implementado.
- **Prêmio PSA 10 ÷ crua** (insumo do passo "prêmio entra no score?"): mediana
  16,6×, p25 5,4×, p5 2,3× — a nota "< 1,5×" quase não dispara; segue
  informativo até o operador decidir.

### Recalibração sobre dado limpo + decisões fechadas (2026-09-22)

O run de 2026-09-21 tinha **20 páginas de outro set** e **5 preços "$0.00"**
no pool (guard conferia só o número — corrigido no #29, ver "Limitações"
item 7). Refeito o run e a calibração sobre o snapshot limpo (300 no teto,
224 com censo confiável, 246 com vendas):

- **Faixas vigentes se sustentam**: Escassez 18 · 13 · 20 · 20 · 18 · 11%,
  Demanda 9 · 35 · 20 · 15 · 21% — nenhuma degenerada (<5% ou >35%). A
  proposta automática do módulo pra Demanda (`30/20/10/1`) cria um degrau com
  **0%** e é pior. **Nada a mexer.** Spearman pop10 × vendas/mês = **+0,83**.
- **Giro como Demanda — REJEITADO com dado.** Giro = vendas/mês ÷ pop10 tem
  Spearman **−0,67** com pop10: vira um SEGUNDO componente de escassez, e o top
  30 enche de BW/HGSS com pop 4-8 e 0,1-0,4 vendas/mês (Darkrai EX #63: pop 4,
  0,2 vendas/mês → 87) — exatamente o "pop baixa sem demanda" que a regra do
  modo exclui. Sobreposição com o top vigente: 14/30. Vendas absolutas ficam.
- **Prêmio no score — REJEITADO com dado.** Spearman prêmio × pop10 = **−0,51**,
  prêmio × vendas = **−0,57**: o prêmio é proxy de escassez (alto onde ninguém
  grada) — entraria contando escassez duas vezes. Segue coluna informativa.
- **Critério de sucesso (fechado):** em janela **≥ 180 dias**, Spearman(score
  em t0, retorno do **PSA 10**) > 0 **e** mediana do top-quartil > mediana do
  bottom-quartil. Implementado em `outlook/validate.py` (`backtest_longitudinal`
  mede no `psa10_usd` quando a história é low pop e imprime o veredito;
  `SUCCESS_MIN_DAYS`). 1ª leitura de pop no PC: `snapshot_2026-09-22.csv`
  (limpo). A 2ª leitura, ≥ 1 mês depois, destrava Δpop10/mês; o veredito do
  critério só a partir de 2027-03.
- Reproduzir a análise do giro: `python -m outlook.lowpop_calibration` dá a
  base; o experimento em si foi ad hoc (script de sessão), números acima.

A detecção de "reprint forte" mora em `outlook/scoring.py`
(`HEAVY_REPRINT_SET_IDS` + `SPECIAL_SET_PREFIX_RE`); a lista de notórios em
`outlook/notorious.py` (`NOTORIOUS_POKEMON`, 60 entradas, portada do
scanner integrado).

A tabela do ranking mostra o **score total** (não mais as 4 parcelas em
colunas — saíram a pedido do operador; o racional dos componentes está acima
e na coluna **Notas**). Cada linha traz o **número junto ao nome** da carta
("Mew V (Alternate Full Art) #251") e a coluna **Links**, no padrão MYP:
**eBay (busca) · TCG · PriceCharting**. O eBay está presente em todas as
linhas, inclusive com `--graded` ou `--doubleholo`, sem precisar de chaves
de API. Abre a busca da carta por nome base, número e coleção na categoria
de cartas individuais, sem exigir graduação (raw também aparece). É busca,
não anúncio verificado ou preço eBay. TCG aponta à referência TCGPlayer;
PriceCharting abre a busca da carta para consultar o histórico visual.

**Coluna DH (opcional, `--doubleholo dh.json`):** uma 2ª opinião de mercado do
Double Holo, nota 0-100 (50=neutro), avaliando os DADOS premium do Double Holo
(previsão de preço + sinal IA + ROI de gradação + momentum). É calculada em
`outlook/doubleholo.py` a partir do JSON canônico gerado por
`scanners-commons/tooling/doubleholo_signals.py ingest --json`, e casada por
**productId do TCGPlayer** (`tcg_product_id` == `card_id`) — join determinístico,
sem casar por nome. **NÃO entra no score** de longo prazo (continua 4×25=100); é
coluna à parte. Carta sem dado Double Holo mostra "—". O JSON vem do DOM-scraper
(`~/doubleholo-scraper/`, no PC do operador), que lê a sessão premium logada sem
tocar no token.

## Onde está mais barata em NM inglês (`run_availability.py`)

> **O que resolve:** pra cada carta do top-N do ranking, responder "onde ela
> está mais barata AGORA em NM inglês", com link direto e veredito honesto.

`python run_availability.py --top 100` recalcula o ranking (fonte tcgcsv,
mesma régua do `run_outlook.py`) e, pra cada carta do top-N, consulta cada
plataforma. Flags: `--top` (default 25), `--eras` (default SV+SWSH+ME),
`--min-price 5.0`, `--max-price 1000.0`. Cobertura **honesta** por plataforma
(`outlook/availability.py`, estado 2026-07):

- **CardTrader** → **preço REAL ao vivo** via API oficial (menor oferta EN+NM
  não-graded PLAUSÍVEL) + link direto da carta. Token `CT_JWT` da **env var**
  (qualquer ambiente, inclusive nuvem) ou do `.env` do repo
  `card-trader-scanner` (PC: `C:\Users\mathe\card-trader-scanner\.env`);
  **nunca é logado/impresso** (sanitização de BOM/zero-width inclusa).
  Robustez do match: blueprint desambiguado pelo NOME além do número;
  nomes de set divergentes têm override explícito (ex.: "Scarlet & Violet
  151" no CT é só "151"; "… Base Set" do SV01/SWSH01 NÃO é o "Base Set"
  WotC; "Pokemon GO" é o "Pokémon TCG: Pokémon GO" internacional, não o
  set japonês homônimo — falsos matches provados em 2026-07-13) e o
  contains é RANQUEADO (não first-hit da API); nº pedido acima da faixa
  numérica do set casado sai como "provável set errado" (autodetecção da
  classe de falso match, sem depender de override); erro transiente da API
  do CT tem retry curto (401 isolado observado entre 2 runs); **anúncio-lixo**
  (<50% da referência market) é pulado e contado — caso real: SIR de
  US$ 118 anunciada "NM EN" por R$ 0,89.
- **TCGPlayer** → preço market de referência + menor anúncio (`lowPrice`,
  condição NÃO filtrada — informativo, NUNCA decide o veredito NM-EN) +
  link direto do produto.
- **eBay** → **preço REAL do menor anúncio ativo** via Browse API oficial
  (grátis; mesmas chaves do ebay-arbitrage-scanner: env vars
  `EBAY_CLIENT_ID`/`EBAY_CLIENT_SECRET`, sanitizadas contra BOM). Guards de
  precisão: nº de coleção obrigatório no título (zeros à esquerda ok), título
  com marcador graded (PSA/BGS/CGC/SGC) ou idioma não-EN é pulado, anúncio
  <50% da ref é lixo contado. Match por BUSCA (não identidade) e condição NM
  NÃO garantida → coluna **informativa**, nunca decide o veredito. Sem as
  chaves → só link (aviso honesto). `--no-ebay` desliga.
- **COMC** → **preço REAL da menor listagem** banda EX-NM + ungraded + Buy It
  Now (filtros server-side na URL de busca), via Firecrawl — **OPT-IN
  `--comc-price`** (cada carta = 1 fetch = créditos pagos da
  `FIRECRAWL_API_KEY`; a COMC é Cloudflare, acesso direto da nuvem = 403).
  Condição por allowlist NM fechada (nunca substring), nº tem que casar, set
  que nomeia idioma não-EN é excluído, lixo <50% da ref contado. Banda EX-NM
  inclui EX e o match é por busca → coluna **informativa**, nunca decide o
  veredito. Sem flag/key → só link, como antes.
- **Liga Pokémon** → SEM preço automatizado (Cloudflare; o coletor headful é
  lento demais pra dezenas de cartas ad-hoc). Link de busca.
- **MYP** → SEM preço automatizado AQUI: a API (`mypcards.com/api/v1`) existe
  mas está atrás de challenge Cloudflare (provado 2026-07 da nuvem: 403 + TLS
  reset via curl_cffi/proxy); cobertura automatizada é do scanner MYP da
  frota. O site também não filtra por querystring → link de busca via Google
  site-restrito.

**Veredito "Mais barato NM-EN"** (`verdict_nm_en`, função pura): compara SÓ
fontes com filtro NM+EN real (hoje: CardTrader) contra a referência market
TCGPlayer; CT abaixo de 50% da ref sai como `⚠️ suspeito`, nunca vencedor;
sem `CT_JWT` sai `n/d` explícito. **Nunca inventa preço**: plataforma sem
coleta automatizada aparece como link pra conferência manual. Decisão de
compra é do operador; a ferramenta só coleta e linka. O `.md` em
`outputs/availability_*.md` é apoio local — a entrega segue sendo a tabela
no chat.

## Limitações honestas (leia antes de usar)

1. **Não é previsão.** É triagem por características historicamente
   associadas a valorização. Mercado pode fazer outra coisa.
2. **Série histórica de preço: agora REAL (com ressalvas).** A "tendência"
   opcional (`--trend`) usa o histórico diário do tcgcsv.com casado por
   `productId` — não é mais a raspagem de ~6 vendas do PriceCharting (a
   mecânica completa está em "Como rodar"). Ressalvas que continuam valendo:
   (a) é **market price agregado**, NÃO por condição (NM/LP); (b) cartas de
   set novo (sem histórico até a janela) saem como `n/d (sem histórico)`, e a
   headline usa a maior janela disponível (ex.: set de 9 meses mostra `(6m)`,
   não `1a`); (c) a Tendência é **informativa e NÃO entra no score** (continua 4×25=100); (d)
   depende do arquivo do tcgcsv (fonte voluntária) e do pacote `py7zr`.
   Mesmo assim, é histórico de fato — não previsão.
3. **Era SWSH**: a API não distingue alt-art de ultra/secret comum pela
   raridade — alt arts SWSH (ex.: Moonbreon) ficam **subpontuadas** no
   componente raridade. A linha ganha nota explicando isso.
4. **Preço do dia.** O run reflete o market price de hoje; rode de novo
   quando quiser o retrato atualizado.
5. **Quem decide capital é o operador.** Score alto = "olhe primeiro".
   Não existe coluna "COMPRAR" de propósito.
6. **A régua NUNCA foi validada como previsão** (auditoria de 2026-09-21).
   A calibração transversal compara com o preço de hoje, e preço é
   componente — mede circularidade; o backtest precisa de snapshots
   acumulados. No `ebay-arbitrage-scanner`, a mesma heurística correlacionou
   +0,43 com o preço e ~0 com o prêmio da PSA 10. Foi isso que motivou o
   modo low pop (escassez e demanda MEDIDAS). As faixas dele foram calibradas
   em 2026-09-21 sobre a DISTRIBUIÇÃO do pool medido ("Calibração das
   faixas") — isso dá discriminação, não prova preditiva: a validação como
   previsão continua dependendo de snapshots acumulados e de um critério de
   sucesso fixado pelo operador (fechado em 2026-09-22 — ver "Recalibração
   sobre dado limpo").
7. **Match carta → página do PriceCharting é por busca de texto**, e o site
   tem números que colidem entre sets. O guard (`outlook/psa10.py`) exige
   **número E set** (productId TCGPlayer da página = do catálogo, OU slug do
   set = nome do catálogo), recusa variante de impressão que o catálogo não
   pediu (`1st-edition`, `shadowless`, `reverse`) e trata `$0.00` como "sem
   dado". Achado do run de 2026-09-21: sem isso, 20/278 consultas "ok" eram
   de outra carta. Cobertura perdida por `&amp;` cru no href da busca (151,
   DP, FRLG, HGSS…) corrigida no mesmo dia. Se um set inteiro sair "sem
   match", suspeite do slug (ex.: `fire-red-&-leaf-green`), não da carta.

## Arquitetura

```
run_outlook.py           CLI principal: baixa catálogo → score → cenário + ranking (+ --sealed, snapshot)
run_availability.py      CLI: onde o top-N está mais barato em NM inglês (CT ao vivo + TCG low + links)
outlook/availability.py  CardTrader NM-EN ao vivo (CT_JWT, filtro de lixo, overrides de set) + links eBay/COMC/Liga/MYP
outlook/ebay_availability.py  eBay Browse API: menor anúncio ativo plausível (EBAY_CLIENT_ID/SECRET; informativo)
outlook/comc_availability.py  COMC via Firecrawl (opt-in --comc-price): menor listagem EX-NM ungraded EN (informativo)
outlook/tcgcsv_api.py    fonte DEFAULT: dumps diários TCGPlayer (cartas + selados)
outlook/ptcg_api.py      cliente pokemontcg.io (sets, cartas, preços TCGPlayer) — fonte alternativa
outlook/scoring.py       os 4 componentes do score + detecção de reprint forte (HEAVY_REPRINT_SET_IDS / SPECIAL_SET_PREFIX_RE)
outlook/sealed.py        score de SELADO (ETB/Box/Bundle/Tin): Tipo + Idade + MSRP + Reimpressão
outlook/notorious.py     lista curada de 60 Pokémon notórios (portada do integrado)
outlook/sets.py          helpers puros de nome de set (strip_era_prefix), compartilhados entre report e availability
outlook/doubleholo.py    coluna DH: nota 0-100 a partir do JSON premium do Double Holo, join por productId
outlook/psa10.py         modos graded/low pop: preço, liquidez, CENSO (pop por nota), crua e TCGPlayer ID do slab via
                         PriceCharting (escada de queries + página de resultados + guard de número + cache 1 dia)
outlook/pricecharting.py tendência best-effort via PriceCharting (--trend-source pricecharting; legado)
outlook/pricehistory.py  tendência REAL: histórico diário do tcgcsv (.ppmd.7z via py7zr), cache data/cache/tcgcsv_history/
outlook/history.py       persiste snapshots diários do score (data/snapshots/) → série histórica própria
outlook/validate.py      calibração transversal do score + backtest longitudinal (usa history)
outlook/lowpop_calibration.py  calibração das FAIXAS do modo low pop: lê snapshot + cache do run, quantis de pop10 e
                         vendas/mês (pool e por era), fatia do pool por faixa vigente × proposta, efeito no topo
outlook/report.py        cenário por era + tabela top-N em markdown
tests/                   228 testes em 16 arquivos: scoring, sealed, history, validate, pricehistory,
                         doubleholo, notorious, report, sets, tcgcsv_api, lowpop, lowpop_calibration,
                         availability, ebay_availability, comc_availability, graded_psa10
```

## Testes e CI

```bash
python -m pytest tests/ -q     # 228 testes (nuvem/Linux: python3)
```

No PC do operador: `.venv\Scripts\python.exe -m pytest tests/ -q`.

Os testes são unitários e **offline** (monkeypatch / lógica pura) — não
precisam de rede nem de `POKEMONTCG_API_KEY`. O CI
(`.github/workflows/ci.yml`, workflow "tests") roda `pytest tests/ -q` em
Python 3.11 a cada push na `main` e em todo PR.

## Fluxo de desenvolvimento e segurança

- Mudanças de código/doc seguem o padrão da frota: **branch + PR**, nunca
  push direto na `main`.
- **Gitignored de propósito** (subprodutos locais, ficam fora do repo):
  `outputs/` (os `.md` de apoio), `data/` (cache do tcgcsv, histórico e
  snapshots), `.venv/`.
- **Segredos nunca versionados nem impressos**: `CT_JWT` é lido do `.env` de
  outro repo (`card-trader-scanner`) e nunca aparece em log;
  `POKEMONTCG_API_KEY` vive em env var.
- Não há `CHANGELOG.md` nem versionamento explícito neste repo — a fonte de
  verdade do estado é a `main`.
- Skills do repo:
  - `.claude/skills/pokemon-longterm/SKILL.md` — o caminho canônico de rodar e
    entregar o ranking. Fixa a régua padrão (`--graded`, PSA 10 — o operador só
    compra graduada), a checagem de pendências antes do run, a entrega VERBATIM
    da tabela do `outlook/report.py` e a fronteira com os scanners de
    arbitragem (pergunta diferente). Espelhado em `~/.claude/skills/` no PC do
    operador e instalável no Cowork pelo `.skill` empacotado — **se editar uma
    cópia, sincronize a outra**.
  - `.claude/commands/auto.md` — comando `/auto` (agente master autônomo da
    frota, sincronizado do `scanners-commons`).
