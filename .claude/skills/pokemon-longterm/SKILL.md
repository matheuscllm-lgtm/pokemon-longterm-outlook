---
name: pokemon-longterm
description: >-
  Ranking de LONGO PRAZO de cartas Pokémon (repo pokemon-longterm-outlook):
  nota 0-100 por carta medida na régua de quem só compra PSA 10, panorama de
  mercado por era e as chases atuais entregues como tabela markdown no chat.
  Use SEMPRE que o operador pedir "long term", "longterm choices", "chases
  atuais", "o que olhar primeiro", "quais cartas têm potencial de valorização",
  "melhores cartas pra segurar", "roda o outlook", "ranking de longo prazo" —
  mesmo que ele não cite o repo nem a ferramenta, e mesmo que peça só "analisa
  as chases". NÃO é arbitragem: pedido de deal, margem, desconto ou "onde está
  mais barato agora" pertence aos scanners (scan-ebay, scan-myp, scan-comc,
  scan-liga, /scan) — são perguntas diferentes.
---

# Ranking de longo prazo (Pokémon) — rodar e entregar

## O que esta ferramenta responde (e o que ela NÃO responde)

Ela olha o catálogo de hoje e pergunta: **quais cartas têm características
historicamente associadas a valorização futura?** Demanda perene do personagem,
tier de raridade, oferta encolhendo (set fora de impressão) e patamar de preço
com espaço pra crescer. O resultado é uma **triagem ordenável** — "olhe isto
primeiro" — não uma previsão e nunca uma recomendação de compra.

O que ela NÃO responde: "onde compro barato agora". Isso é arbitragem, mora nos
scanners irmãos. Se o operador misturar as duas coisas num pedido só, rode esta
primeiro (define O QUE olhar) e depois ofereça o scanner (define ONDE comprar) —
ver a seção de handoff no fim.

## A régua padrão é PSA 10 — use `--graded`

**O operador compra exclusivamente carta graduada, foco PSA 10** (decisão dele,
2026-09-01). O componente de Preço do score nasceu calibrado em carta CRUA, que
é a régua errada pra esse funil: ranqueia pela liquidez de um mercado que ele
não compra. A flag `--graded` remede o Preço no **slab PSA 10** (preço justo de
vendas reais + vendas/mês de liquidez), e os outros três componentes não mudam.

Rodar sem `--graded` entrega um ranking bonito e **enganoso pra este operador** —
o Charizard ex #223, por exemplo, vira topo pela régua raw ($104) e cai pro meio
da tabela pela régua do slab ($777, faixa "já precificado"). Só rode a régua raw
se ele pedir explicitamente carta crua.

## Passo 1 — pendências antes de rodar (2 min)

O operador costuma pedir "avalie as pendências" junto. Vale a pena mesmo quando
ele não pede, porque um PR aberto pode significar que a ferramenta que você está
prestes a rodar tem um defeito conhecido.

```bash
cd <repo>/pokemon-longterm-outlook
git fetch origin main -q && git log --oneline -5 origin/main
```

Depois liste PRs abertos e o CI da `main` (ferramentas `mcp__github__*`; o `gh`
CLI não existe nas sessões de nuvem). **O teste real de "esse PR ainda vale" é
ler o código, não o título**: outras sessões trabalham nos mesmos repos, e já
aconteceu de um PR aberto ter o conserto *já presente na `main`* por outro
caminho. Confira se a função que ele muda já está corrigida no `origin/main`
antes de reportar como pendência viva.

Se um PR estiver superado ou em conflito, **relate e recomende fechar — não
feche por conta própria**: PR de outra sessão não é seu pra encerrar.

## Passo 2 — rodar

```bash
python run_outlook.py --graded          # nuvem/Linux
# PC do operador: .venv\Scripts\python.exe run_outlook.py --graded
```

Leva de 5 a 10 minutos (baixa o catálogo das 3 eras e consulta o PriceCharting
carta a carta com pausa educada de ~1,5s). **Rode em segundo plano** e avise o
operador que está rodando — run longo em primeiro plano some se a sessão for
interrompida.

Flags que mudam o resultado, quando ele pedir:

| Pedido dele | Flag |
|---|---|
| "mostra mais cartas" | `--top 100` (o pool graded acompanha: 2× o top, mínimo 50) |
| "e a tendência de preço?" | `--trend` — **exige `py7zr`** (`pip install py7zr`); sem o pacote a coluna sai `—`, honestamente |
| "e os selados?" | `--sealed` |
| "quero ver carta mais barata também" | `--min-price 20` / `--max-price` ajustam o universo |
| "2ª opinião do Double Holo" | `--doubleholo <json>` |

## Passo 3 — entregar a tabela VERBATIM

A formatação canônica vive em `outlook/report.py`. O run imprime a tabela pronta
e grava uma cópia em `outputs/outlook_<stamp>.md`. **Cole essa saída no chat sem
mexer**: não remonte colunas, não corte linhas, não "resuma" a tabela, não tire
os links.

Isso não é preciosismo de formato. A tabela carrega, por linha, o preço do slab,
a liquidez, o preço raw como contexto e três links de conferência (eBay, TCG,
PriceCharting). Uma tabela remontada à mão perde justamente o que permite ao
operador auditar o número antes de mover capital — e já foi a causa de erro
recorrente na frota.

Arquivo (`.md`, `.xlsx`) **só se ele pedir explicitamente**. O `outputs/` é apoio
local, a entrega é a tabela no chat.

## Passo 4 — a leitura das chases (curta, factual)

Depois da tabela, 3 a 6 linhas explicando o que o ranking está dizendo. O que
costuma ser útil:

- **o padrão do topo** (ex.: "alt arts de SWSH fora de impressão, slab na faixa
  $120-360 e 30 vendas/mês" — junta os 4 componentes numa frase);
- **quem saiu do topo e por quê** (carta cara demais cai pra faixa "já
  precificado" — mostra a régua funcionando, não é demérito da carta);
- **cobertura honesta**: o run informa quantas cartas do pool tiveram PSA 10
  real (ex.: 95/100); as demais mantiveram a régua raw com o motivo na linha.
  Reporte isso — é a diferença entre dado e chute;
- **o que ficou `—`** e por quê (tendência sem `py7zr`, por exemplo).

O que **não** fazer: rankear "compre esta", sugerir alocação de capital, ou
transformar score alto em conselho. Score alto = "olhe primeiro". A decisão de
capital é 100% do operador, e a ferramenta não tem coluna "COMPRAR" de propósito.

## Ambiente: repo presente ou não

**Claude Code com o repo aberto** (caso comum): rode direto, como acima.

**Cowork, ou qualquer sessão sem o repo**: clone antes —
`matheuscllm-lgtm/pokemon-longterm-outlook` — e instale as dependências
(`requests`, `py7zr` se for usar tendência). Nenhuma chave de API é necessária
pro ranking: a fonte default (`tcgcsv`, dump diário do TCGPlayer) é pública.
`POKEMONTCG_API_KEY` só acelera a fonte alternativa.

**Se não der pra rodar a ferramenta** (sem rede, sem repo, sem Python): diga
isso e pare. Não monte um ranking de memória nem reaproveite uma tabela de um
run antigo como se fosse de hoje — os preços mudam todo dia, e um número
inventado aqui vira decisão de capital errada lá na frente.

## Armadilhas conhecidas (não re-descobrir)

- **Alt arts de SWSH ficam subpontuadas** no componente Raridade: a fonte não
  distingue alt art de ultra/secret comum nessa era. A linha já sai com nota
  explicando; mencione se alguma carta óbvia (Moonbreon e cia.) aparecer mais
  baixa do que o esperado.
- **Sets com reprint forte** (151, Prismatic, Celebrations…) têm o componente
  Supply tetado em 12 de propósito: a oferta não encolhe. Não é bug.
- **Slab ilíquido** (< 3 vendas/mês) teta o Preço em 12 — preço de tabela num
  mercado que quase não negocia não é preço realizável. Liquidez **desconhecida**
  NÃO teta: ausência de dado não é sinal de iliquidez.
- **`--graded-pool` ≠ `--top`**: o ranking raw escolhe quem vale consultar no
  PriceCharting; só então o Preço é remedido. Se o operador pedir top 100, o
  pool vai a 200 consultas e o run dobra de tempo — avise antes.

## Handoff: do "o que olhar" pro "onde comprar"

Terminada a entrega, o passo natural é cruzar as chases com anúncios reais. O
scanner do eBay (repo `ebay-arbitrage-scanner`) roda **por grupo canônico
(1–12), um por vez** — os grupos 11 e 12 (SWSH 2020-2022) costumam cobrir a
maior parte do topo deste ranking. Ofereça, não execute por conta: é outro repo,
outras regras econômicas e um run longo.

Há também `run_availability.py --top N` neste mesmo repo, que responde onde cada
carta do topo está mais barata em NM inglês (CardTrader ao vivo + links). É
complementar, não substitui os scanners.
