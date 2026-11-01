---
name: psa10-hunt
description: >-
  Caça a exemplares RAW de uma carta Pokémon específica com maior potencial
  visual de PSA 10: pesquisa anúncios no eBay e/ou COMC, inspeciona as fotos
  reais de CADA exemplar (centering medido por pixels, cantos, bordas,
  superfície, impressão) e entrega ranking comparativo com veredito honesto.
  Use quando o operador pedir "/psa10-hunt", "acha exemplar pra gradar",
  "qual desses tem cara de PSA 10", "compara esses anúncios pra gradação",
  ou fornecer fotos/links de uma carta perguntando o potencial de nota.
  NÃO é o ranking de longo prazo (/pokemon-longterm decide O QUE olhar;
  esta skill avalia EXEMPLARES de UMA carta já escolhida) e NÃO é
  arbitragem de preço (scanners da frota).
---

# PSA 10 Hunt — achar o melhor exemplar raw de UMA carta

## O que esta skill responde (e o que NÃO responde)

Dada uma carta específica (ex.: `Kadabra 32/102`), responde: **entre os
exemplares raw anunciados agora, quais têm as melhores características
visuais para tentar PSA 10?** A resposta é um ranking comparativo de
exemplares REAIS (um anúncio = um exemplar), com centering medido, defeitos
observados e limitações declaradas.

O que ela NÃO faz: não garante nota, não inventa probabilidade numérica de
gem, não recomenda compra (decisão de capital é do operador), não compra nem
envia mensagem a vendedor sem pedido explícito. **População PSA 10 baixa não
é chance individual** — não confunda censo com o exemplar na mesa.

## Entrada

O operador informa a carta (ex.: `Kadabra 32/102`) e, opcionalmente: fotos
próprias, links de anúncios, idioma, edição/variante, orçamento e
marketplaces. Fotos/links fornecidos têm **prioridade** sobre a busca.

## Passo 1 — Identificação e escopo (antes de qualquer busca)

Confirme: **coleção, número, idioma e variante** — 1st Edition, Shadowless,
Unlimited, holo/reverse ou outras pertinentes àquele set. **Nunca misture
variantes no mesmo ranking** (1st Edition e Unlimited são mercados e censos
diferentes; no PriceCharting são até páginas separadas).

Se faltar informação **determinante** (variante ambígua, orçamento quando há
dispersão grande de preço, idioma): use a skill **Grill Me**
(`anthropic-skills:grill-me`) se disponível para perguntas curtas e
objetivas; senão pergunte diretamente. Antes de perguntar, esgote o contexto
já disponível (mensagens, fotos, links, catálogo tcgcsv do repo) — não faça
pergunta cuja resposta já está na mesa.

## Passo 2 — Pesquisa de exemplares

Plataformas: **eBay e/ou COMC**, conforme indicação do operador; sem
indicação, **consulte ambas**.

- **eBay**: priorize anúncios com fotos reais do exemplar vendido. As
  credenciais da frota (`EBAY_CLIENT_ID`/`EBAY_CLIENT_SECRET`, as mesmas de
  `outlook/ebay_availability.py`) permitem a Browse API para listar anúncios
  ativos; as fotos do anúncio vêm das URLs de imagem do item (a API expõe
  `image`/`additionalImages`). Sem as chaves, busca via web com link honesto.
- **COMC**: use os scans de frente e verso do item específico, ampliados
  (a COMC serve o scan em resolução maior trocando o parâmetro de tamanho da
  URL da imagem). Acesso direto da nuvem pode dar 403 (Cloudflare) — o
  caminho pago via Firecrawl (`FIRECRAWL_API_KEY`) é **opt-in**, como no
  `--comc-price`; sem ele, declare a limitação.

Filtros duros de inclusão:

- Mesma **variante** confirmada no passo 1 — fora dela, exclui.
- **Fotos do exemplar real**: exclua foto genérica/stock, anúncio "random
  card" e item sem imagens suficientes pra avaliar. Exclusão é registrada
  ("N anúncios descartados: foto genérica"), não silenciosa.
- "Mint"/"Near Mint" na descrição **não substitui inspeção visual** — é
  claim do vendedor, não dado.

Registre por exemplar: plataforma, identificação do item (item ID/SKU),
**link direto**, preço, custos adicionais disponíveis (frete/importação, se
expostos) e **data da consulta**. Scans podem ocultar riscos, amassados e
alteração de brilho — essa ressalva acompanha qualquer avaliação via COMC.

## Passo 3 — Ferramentas e centering (medir, não estimar de olho)

Descubra o que a sessão realmente tem antes de prometer método: Python +
OpenCV/Pillow para medição por pixels, Playwright/navegador para abrir e
ampliar anúncios, tool de leitura de imagem para inspeção visual. **Nunca
alegue ter usado ferramenta indisponível** — se só deu pra inspeção visual
sem medição, o relatório diz isso.

Ordem de preferência: **medição reproduzível por pixels** (OpenCV: detectar
borda externa da carta e limite da área impressa correta PARA AQUELE design,
contar pixels de margem) > ferramenta dedicada de centering > estimativa
visual declarada como tal.

- Examine **frente e verso em resolução original**. Corrija perspectiva só
  quando tecnicamente confiável (homografia com os 4 cantos bem detectados);
  preserve a imagem original. **Proibido** preenchimento generativo ou
  qualquer "aprimoramento" que possa inventar detalhe.
- Meça os dois eixos separadamente, bordas externas vs. limites corretos da
  impressão daquele design:
  - Horizontal: `E/(E+D)` e `D/(E+D)`
  - Vertical: `S/(S+I)` e `I/(S+I)`
- Apresente proporções percentuais **com método e incerteza** (ex.: "58/42
  ±3 p.p., foto em ângulo"). Não reporte precisão que a foto não sustenta
  (foto de celular torta não dá 55,2/44,8).
- Consulte os critérios oficiais vigentes em
  <https://www.psacard.com/gradingstandards> (não confie na memória — a PSA
  muda a redação). Referência inicial: PSA 10 ≈ **55/45 ou melhor na frente**
  e **75/25 no verso**. Avalie ambos os eixos; priorize exemplares com
  **margem confortável**, não no limite.
- Gere recortes ampliados e sobreposições das linhas de medição quando
  possível (apoio em `outputs/` ou scratchpad; anexar só sob pedido).
- Perspectiva ruim, reflexo, sleeve/toploader ou resolução baixa impedindo
  medição confiável → **"não mensurável"**, nunca um número chutado. É o
  mesmo princípio do `n/d` honesto da frota.

## Passo 4 — Inspeção além do centering

Avalie individualmente, frente e verso:

- **Quatro cantos**: desgaste, arredondamento, pontos brancos.
- **Bordas**: whitening, lascas, corte irregular.
- **Superfície**: riscos, amassados, vincos, manchas, marcas de pressão.
- **Impressão**: print lines, falhas, registro, foco, brilho original.
- **Indícios de alteração/autenticidade duvidosa**: registre como suspeita
  quando houver sinal; **nunca afirme conclusão que as fotos não sustentam**.

Classifique cada observação em três níveis distintos: **"defeito
observado"** (visível na foto), **"suspeita"** (sinal ambíguo) e **"não
avaliável"** (a foto não cobre). Ausência de defeito visível **não comprova
ausência de defeito** — scans e fotos de anúncio escondem exatamente os
defeitos de superfície que mais derrubam nota.

## Passo 5 — Resultado (tabela no chat, padrão da frota)

Tabela ordenada por potencial, colunas: **posição · exemplar/link ·
variante · preço (+custos quando houver) · centering frente (H e V) ·
centering verso (H e V) · defeitos · limitações · confiança ·
recomendação**. Centering não mensurável sai como "não mensurável", nunca
em branco nem estimado.

Recomendação usa exatamente estas classes:

- **candidato forte** — centering com folga nos dois lados E nenhum defeito
  observado E fotos suficientes;
- **candidato condicionado a novas fotos** — promissor, mas com "não
  avaliável" em área determinante;
- **descartar para objetivo PSA 10** — defeito observado incompatível com
  gem, ou centering fora com medição confiável;
- **evidência insuficiente** — fotos não permitem avaliação séria.

Feche com: os melhores candidatos + justificativa curta + **quais fotos
adicionais pedir** (ex.: verso sem sleeve, canto inferior direito em
macro, foto em ângulo contra a luz pra superfície). Regras finais:

- Boa centralização **isoladamente não basta** — um candidato forte precisa
  passar em centering E inspeção.
- Se **nenhum** exemplar atende, diga claramente e pare — ranking vazio
  honesto vale mais que um "melhor dos ruins" disfarçado de candidato.
- Nada de probabilidade numérica inventada, nada de garantia de nota, nada
  de "COMPRE" — handoff natural: skills de grading da frota
  (`ativar-grading-cards-psa`) quando o operador decidir enviar.
