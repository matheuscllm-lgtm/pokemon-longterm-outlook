# Pokémon Long-Term Outlook

Panorama do mercado Pokémon TCG por era + score 0-100 de potencial de longo
prazo por carta (heurística transparente: personagem + raridade + supply +
preço). Dados: pokemontcg.io (preços TCGPlayer) e, opcionalmente,
PriceCharting público para tendência.

**Não é conselho de investimento.** A ferramenta ranqueia e explica; a
decisão é sempre do operador. Documentação completa (em linguagem acessível):
[CLAUDE.md](CLAUDE.md).

```powershell
.venv\Scripts\python.exe run_outlook.py --top 50
```
