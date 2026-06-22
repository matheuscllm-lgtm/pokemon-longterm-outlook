# Pokémon Long-Term Outlook

Panorama do mercado Pokémon TCG por era + score 0-100 de potencial de longo
prazo por carta (heurística transparente: personagem + raridade + supply +
preço). Dados: tcgcsv.com (dump diário do TCGPlayer, fonte default) — com
`pokemontcg.io` como alternativa via `--source ptcg`. A tendência opcional
(`--trend`) usa o **histórico de preço REAL** do tcgcsv (série diária desde
2024-02-08, casada por productId), não previsão.

**Não é conselho de investimento.** A ferramenta ranqueia e explica; a
decisão é sempre do operador. Documentação completa (em linguagem acessível):
[CLAUDE.md](CLAUDE.md).

```powershell
.venv\Scripts\python.exe run_outlook.py --top 50            # ranking
.venv\Scripts\python.exe run_outlook.py --top 30 --trend   # + histórico real
```
