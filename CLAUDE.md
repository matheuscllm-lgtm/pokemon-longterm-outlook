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

> **Manual completo da frota** (repo privado):
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
.venv\Scripts\python.exe run_availability.py --top 25  # disponibilidade por plataforma do top-N
.venv\Scripts\python.exe -m outlook.history            # resumo da série histórica (maiores altas/quedas)
.venv\Scripts\python.exe -m outlook.validate           # calibração do score + backtest (quando houver história)
```

Na nuvem/Linux, os mesmos comandos com `python3` (ou `.venv/bin/python`), ex.:
`python3 run_outlook.py --trend`.

**Defaults do CLI (`run_outlook.py`)**: `--top 50` · `--min-price 5.0` ·
`--max-price 1000.0` · `--eras` default = `Scarlet & Violet`, `Sword & Shield`,
`Mega Evolution` (`DEFAULT_ERAS`) · `--source {tcgcsv,ptcg}` default `tcgcsv` ·
`--trend-source {tcgcsv,pricecharting}` default `tcgcsv` · `--no-snapshot`
pula o snapshot diário.

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

A detecção de "reprint forte" mora em `outlook/scoring.py`
(`HEAVY_REPRINT_SET_IDS` + `SPECIAL_SET_PREFIX_RE`); a lista de notórios em
`outlook/notorious.py` (`NOTORIOUS_POKEMON`, 60 entradas, portada do
scanner integrado).

A tabela do ranking mostra o **score total** (não mais as 4 parcelas em
colunas — saíram a pedido do operador; o racional dos componentes está acima
e na coluna **Notas**). Cada linha traz o **número junto ao nome** da carta
("Mew V (Alternate Full Art) #251") e dois links: **TCG** (TCGPlayer) e
**Gráfico (PriceCharting)** — busca que cai na página da carta no
PriceCharting, onde fica o histórico visual de preço.

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

## Disponibilidade por plataforma (`run_availability.py`)

> **O que resolve:** pra cada carta do top-N do ranking, responder "onde ela
> está acessível AGORA e por quanto", com link direto.

`python run_availability.py --top 25` recalcula o ranking (fonte tcgcsv, mesma
régua do `run_outlook.py`) e, pra cada carta do top-N, consulta cada
plataforma. Flags: `--top` (default 25), `--eras` (default SV+SWSH+ME),
`--min-price 5.0`, `--max-price 1000.0`. Cobertura **honesta** por plataforma
(`outlook/availability.py`, estado 2026-06):

- **CardTrader** → **preço REAL ao vivo** via API oficial (menor oferta EN+NM
  não-graded) + link direto da carta. O token `CT_JWT` é lido do `.env` do
  repo `card-trader-scanner` (PC do operador:
  `C:\Users\mathe\card-trader-scanner\.env`) e **nunca é logado/impresso**.
- **TCGPlayer** → preço market de referência (já vem do ranking/tcgcsv) +
  link direto do produto.
- **eBay** → SEM preço automatizado (Browse API exige keys não criadas neste
  contexto; scrape = 403). Link de busca.
- **COMC** → SEM preço automatizado (exige navegador real/headful pra passar
  o Cloudflare). Link de busca.
- **Liga Pokémon** → SEM preço automatizado (Cloudflare; o coletor headful é
  lento demais pra dezenas de cartas ad-hoc). Link de busca.
- **MYP** → SEM preço automatizado E SEM busca por URL (o site só filtra via
  JavaScript; testado `?busca`/`?q`/`?nome`/`?s` — nenhum filtra). Link de
  busca via Google site-restrito.

**Nunca inventa preço**: plataforma sem coleta automatizada aparece como link
pra conferência manual, explicitamente. Decisão de compra é do operador; a
ferramenta só coleta e linka. O `.md` em `outputs/availability_*.md` é apoio
local — a entrega segue sendo a tabela no chat.

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

## Arquitetura

```
run_outlook.py           CLI principal: baixa catálogo → score → cenário + ranking (+ --sealed, snapshot)
run_availability.py      CLI de disponibilidade por plataforma pro top-N (CT ao vivo + links)
outlook/tcgcsv_api.py    fonte DEFAULT: dumps diários TCGPlayer (cartas + selados)
outlook/ptcg_api.py      cliente pokemontcg.io (sets, cartas, preços TCGPlayer) — fonte alternativa
outlook/scoring.py       os 4 componentes do score + detecção de reprint forte (HEAVY_REPRINT_SET_IDS / SPECIAL_SET_PREFIX_RE)
outlook/sealed.py        score de SELADO (ETB/Box/Bundle/Tin): Tipo + Idade + MSRP + Reimpressão
outlook/notorious.py     lista curada de 60 Pokémon notórios (portada do integrado)
outlook/availability.py  disponibilidade por plataforma: CardTrader ao vivo (CT_JWT) + links eBay/COMC/Liga/MYP
outlook/sets.py          helpers puros de nome de set (strip_era_prefix), compartilhados entre report e availability
outlook/doubleholo.py    coluna DH: nota 0-100 a partir do JSON premium do Double Holo, join por productId
outlook/pricecharting.py tendência best-effort via PriceCharting (--trend-source pricecharting; legado)
outlook/pricehistory.py  tendência REAL: histórico diário do tcgcsv (.ppmd.7z via py7zr), cache data/cache/tcgcsv_history/
outlook/history.py       persiste snapshots diários do score (data/snapshots/) → série histórica própria
outlook/validate.py      calibração transversal do score + backtest longitudinal (usa history)
outlook/report.py        cenário por era + tabela top-N em markdown
tests/                   74 testes em 10 arquivos: scoring, sealed, history, validate, pricehistory,
                         doubleholo, notorious, report, sets, tcgcsv_api
```

## Testes e CI

```bash
python -m pytest tests/ -q     # 74 testes (nuvem/Linux: python3)
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
- Skill do repo: `.claude/commands/auto.md` — comando `/auto` (agente master
  autônomo da frota, sincronizado do `scanners-commons`).
