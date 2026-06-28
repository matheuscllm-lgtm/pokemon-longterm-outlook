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
.venv\Scripts\python.exe run_outlook.py --trend        # + tendência REAL (histórico tcgcsv)
.venv\Scripts\python.exe run_outlook.py --top 30 --min-price 20
.venv\Scripts\python.exe run_outlook.py --sealed       # + ranking de selados (ETB/Box/Bundle/Tin)
.venv\Scripts\python.exe run_outlook.py --doubleholo dh.json  # + coluna DH (2ª opinião Double Holo)
.venv\Scripts\python.exe -m outlook.history            # resumo da série histórica (maiores altas/quedas)
.venv\Scripts\python.exe -m outlook.validate           # calibração do score + backtest (quando houver história)
```

`--trend` agora usa **histórico de preço REAL** do tcgcsv.com (dumps diários do
TCGPlayer desde 2024-02-08), casado por `productId` — a variação entre hoje e o
ponto mais distante disponível (até 1 ano). É a fonte default da tendência
(`--trend-source tcgcsv`); a antiga raspagem do PriceCharting segue acessível em
`--trend-source pricecharting` (indício fraco, ~6 vendas). O histórico exige
`--source tcgcsv` (o casamento é por productId) e o pacote `py7zr` (lê o `.7z`
PPMd); sem ele a tendência cai pra `n/d` honestamente, sem quebrar o run. Os
dumps ficam em cache em `data/cache/` (1ª vez ~9s/ponto; depois instantâneo).

Além disso, cada run salva um **snapshot diário do score** em `data/snapshots/`
(use `--no-snapshot` para pular) — a memória própria da ferramenta, que alimenta
a validação/backtest longitudinal (`outlook/validate.py`).

Precisa da `POKEMONTCG_API_KEY` (User env var — já está configurada nesta
máquina; key grátis em dev.pokemontcg.io). Sem a key roda também, só mais
devagar/limitado.

A entrega é a **tabela markdown no terminal/chat** (regra do operador:
resultado = tabela no chat, nunca arquivo por padrão). O `.md` em `outputs/`
é apoio local.

## Como o score funciona (0-100 = soma de 4 componentes 0-25)

| Componente | O que mede | Como pontua |
|---|---|---|
| **Personagem** | demanda perene do Pokémon | notório (lista curada ~55: Charizard, Umbreon, Pikachu...) = 25; resto = 8 |
| **Raridade** | tier colecionável | SIR/alt-art 25 · IR 20 · TG/Character/**Mega Attack** 16 · gold/secret/shiny/**Mega Hyper** 14 · ultra/VMAX 12 · ACE SPEC 10 · double rare/Rare Holo V 6 · resto 3 |
| **Supply** | oferta encolhendo | ≥36 meses = 25 · 24-36m = 22 · 18-24m = 18 · 12-18m = 12 · 6-12m = 7 · <6m = 3; set com **reprint forte** trava em 12 |
| **Preço** | espaço pra crescer com liquidez | $40-120 = 25 · $15-40 = 20 · >$300 = 12 (já precificado) · <$5 = 5 (sem liquidez) |

A tabela do ranking mostra o **score total** (não mais as 4 parcelas em
colunas — saíram a pedido do operador; o racional dos componentes está acima
e na coluna **Notas**).

**Coluna DH (opcional, `--doubleholo dh.json`):** uma 2ª opinião de mercado do
Double Holo, nota 0-100 (50=neutro), avaliando os DADOS premium do Double Holo
(previsão de preço + sinal IA + ROI de gradação + momentum). É calculada em
`outlook/doubleholo.py` a partir do JSON canônico gerado por
`scanners-commons/tooling/doubleholo_signals.py ingest --json`, e casada por
**productId do TCGPlayer** (`tcg_product_id` == `card_id`) — join determinístico,
sem casar por nome. **NÃO entra no score** de longo prazo (continua 4×25=100); é
coluna à parte. Carta sem dado Double Holo mostra "—". O JSON vem do DOM-scraper
(`~/doubleholo-scraper/`), que lê a sessão premium logada sem tocar no token. Cada linha traz o **número junto ao nome** da carta
("Mew V (Alternate Full Art) #251") e dois links: **TCG** (TCGPlayer) e
**Gráfico (PriceCharting)** — busca que cai na página da carta no
PriceCharting, onde fica o histórico visual de preço.

## Limitações honestas (leia antes de usar)

1. **Não é previsão.** É triagem por características historicamente
   associadas a valorização. Mercado pode fazer outra coisa.
2. **Série histórica de preço: agora REAL (com ressalvas).** A "tendência"
   opcional (`--trend`) usa o **histórico diário do tcgcsv.com** (marketPrice
   TCGPlayer desde 2024-02-08), casado por `productId` — não é mais a raspagem
   de ~6 vendas do PriceCharting. Ressalvas que continuam valendo: (a) é
   **market price agregado**, NÃO por condição (NM/LP); (b) cartas de set novo
   (sem histórico até a janela) saem como `n/d (sem histórico)`, e a headline
   usa a maior janela disponível (ex.: set de 9 meses mostra `(6m)`, não `1a`);
   (c) a Tendência é **informativa e NÃO entra no score** (continua 4×25=100);
   (d) depende do arquivo do tcgcsv (fonte voluntária) e do pacote `py7zr`.
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
run_outlook.py           CLI: baixa catálogo → score → cenário + ranking (+ --sealed, snapshot)
outlook/tcgcsv_api.py    fonte DEFAULT: dumps diários TCGPlayer (cartas + selados)
outlook/ptcg_api.py      cliente pokemontcg.io (sets, cartas, preços TCGPlayer) — fonte alternativa
outlook/scoring.py       os 4 componentes do score + detecção de set especial (reprint forte)
outlook/sealed.py        score de SELADO (ETB/Box/Bundle/Tin): Tipo + Idade + MSRP + Reimpressão
outlook/notorious.py     lista curada de ~55 Pokémon notórios (portada do integrado)
outlook/pricecharting.py tendência best-effort via PriceCharting (--trend-source pricecharting; legado)
outlook/pricehistory.py  tendência REAL: histórico diário do tcgcsv (.ppmd.7z via py7zr), casado por productId
outlook/history.py       persiste snapshots diários do score (data/snapshots/) → série histórica própria
outlook/validate.py      calibração transversal do score + backtest longitudinal (usa history)
outlook/report.py        cenário por era + tabela top-N em markdown
tests/                   testes de scoring, sealed, history, validate e do histórico de preço
```

Rodar os testes:

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```
