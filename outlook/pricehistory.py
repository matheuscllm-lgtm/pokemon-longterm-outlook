"""Histórico REAL de preço TCGPlayer via arquivos diários do tcgcsv.com.

Por que existe: a fraqueza nº 1 declarada do scorer era *"sem série histórica
de preço"* — a tendência (`--trend`) vinha de ~6 vendas raspadas do
PriceCharting (amostra minúscula, indício apenas). O tcgcsv.com mantém um
ARQUIVO de preços com snapshots **diários desde 2024-02-08** (o MESMO
`marketPrice` TCGPlayer que já usamos pro preço do dia), em `.ppmd.7z`.

Aqui baixamos alguns pontos de referência (30/90/180/365 dias atrás), extraímos
a categoria Pokémon (`3`) e calculamos uma tendência de VERDADE — casada por
`productId` (= o `id` que o `tcgcsv_api` já usa como id da carta), sem matching
difuso. O ponto pesado (descompressão PPMd, ~9s/arquivo) roda UMA vez por data
de referência e fica em cache em disco; os runs seguintes são instantâneos.

Honestidade (regra dura do projeto):
- Sem `py7zr` instalado → `n/d (py7zr ausente)`; o run NUNCA quebra por isso.
- Data anterior a 2024-02-08 ou arquivo do dia ausente → aquele ponto é pulado.
- Carta sem preço naquela data (set ainda não existia) → ponto ignorado; sem
  nenhum ponto → `n/d (sem histórico)`. NUNCA inventa preço.

Dependência: `py7zr` (vem no requirements). O formato `.ppmd.7z` usa o filtro
PPMd, que `zipfile`/`lzma` da stdlib NÃO leem — `py7zr` (via `pyppmd`) é o leitor.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

import requests

ARCHIVE_URL = "https://tcgcsv.com/archive/tcgplayer/prices-{d}.ppmd.7z"
HEADERS = {"User-Agent": "pokemon-longterm-outlook/0.1"}
EARLIEST = date(2024, 2, 8)          # início do arquivo do tcgcsv (FAQ)
POKEMON_CATEGORY = "3"               # categoria Pokémon no TCGPlayer
TIMEOUT_S = 60
DEFAULT_WINDOWS = (30, 90, 180, 365)  # dias atrás = pontos de referência
THRESHOLD_PCT = 8.0                  # |%| pra a seta deixar de ser "estável"
HORIZON_LABELS = {30: "1m", 90: "3m", 180: "6m", 365: "1a"}

CACHE_DIR = (Path(__file__).resolve().parent.parent
             / "data" / "cache" / "tcgcsv_history")


# --------------------------------------------------------------------------- #
# py7zr é opcional e carregado preguiçosamente — sem ele, o módulo importa
# normalmente e a tendência cai pra "n/d (py7zr ausente)".
# --------------------------------------------------------------------------- #
def _py7zr():
    try:
        import py7zr  # noqa: WPS433 (import local proposital)
        return py7zr
    except ImportError:
        return None


def py7zr_available() -> bool:
    return _py7zr() is not None


@dataclass
class Trend:
    """Resultado de tendência por carta — string pronta + componentes abertos."""
    label: str
    pct_long: Optional[float] = None     # variação na maior janela disponível
    horizon_long: str = ""               # rótulo dessa janela ("1a", "6m"...)
    pct_recent: Optional[float] = None    # variação ~90d (momentum), se houver


# --------------------------------------------------------------------------- #
# Datas de referência
# --------------------------------------------------------------------------- #
def target_dates(today: date,
                 windows: tuple[int, ...] = DEFAULT_WINDOWS) -> dict[int, date]:
    """{janela_em_dias: data_alvo}, clampado a >= EARLIEST e < hoje."""
    out: dict[int, date] = {}
    for w in windows:
        d = today - timedelta(days=w)
        if d < EARLIEST or d >= today:
            continue
        out[w] = d
    return out


# --------------------------------------------------------------------------- #
# Download + extração (com cache em disco)
# --------------------------------------------------------------------------- #
def _archive_path(d: date) -> Path:
    return CACHE_DIR / f"prices-{d.isoformat()}.ppmd.7z"


def _map_path(d: date) -> Path:
    return CACHE_DIR / f"cat3-{d.isoformat()}.json"


def _download(d: date) -> Optional[Path]:
    """Baixa o `.7z` do dia (cacheado). 404/erro → None (dia ausente)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ap = _archive_path(d)
    if ap.exists() and ap.stat().st_size > 0:
        return ap
    try:
        r = requests.get(ARCHIVE_URL.format(d=d.isoformat()),
                         headers=HEADERS, timeout=TIMEOUT_S)
    except requests.RequestException:
        return None
    if r.status_code != 200 or not r.content:
        return None
    ap.write_bytes(r.content)
    return ap


def _best_market_from_rows(rows: list[dict]) -> dict[str, float]:
    """{productId(str): maior `marketPrice` não-reverse} — mesma regra do live.

    Espelha `tcgcsv_api.fetch_cards_with_prices`: ignora "Reverse Holofoil" e,
    havendo várias variantes do mesmo produto, fica com a de maior market.
    """
    best: dict[str, float] = {}
    for r in rows:
        if "reverse" in (r.get("subTypeName") or "").lower():
            continue
        m = r.get("marketPrice")
        if isinstance(m, (int, float)) and m > 0:
            pid = str(r.get("productId"))
            if m > best.get(pid, 0.0):
                best[pid] = float(m)
    return best


def _map_from_extracted(root: Path) -> dict[str, float]:
    """Varre `<root>/<data>/3/<group>/prices` e devolve {productId: market}.

    Casa a categoria pelo penúltimo-2 segmento do caminho (`.../3/<grp>/prices`),
    então um `.../1/3/prices` (categoria 1, grupo 3) é corretamente excluído.
    """
    out: dict[str, float] = {}
    for fp in root.rglob("prices"):
        parts = fp.parts
        if len(parts) >= 3 and parts[-3] == POKEMON_CATEGORY:
            try:
                obj = json.loads(fp.read_text())
            except (ValueError, OSError):
                continue
            out.update(_best_market_from_rows(obj.get("results", [])))
    return out


def _extract_cat3_map(archive: Path) -> dict[str, float]:
    """Extrai só os `prices` da categoria 3 do `.7z` → {productId: market}."""
    py7zr = _py7zr()
    if py7zr is None:
        raise RuntimeError("py7zr ausente")
    with py7zr.SevenZipFile(archive, "r") as z:
        names = z.getnames()
    targets = [n for n in names
               if n.split("/")[1:2] == [POKEMON_CATEGORY]
               and n.endswith("/prices")]
    if not targets:
        return {}
    tmp = Path(tempfile.mkdtemp(prefix="tcgcsv_hist_"))
    try:
        with py7zr.SevenZipFile(archive, "r") as z:
            z.extract(path=str(tmp), targets=targets)
        return _map_from_extracted(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def price_map_for_date(d: date) -> Optional[dict[str, float]]:
    """{productId: market} pra um dia. Usa cache JSON; None se indisponível.

    Tenta o dia e até 2 dias anteriores (o arquivo às vezes pula um dia).
    Retorna None tanto quando `py7zr` falta quanto quando não há arquivo.
    """
    for back in (0, 1, 2):
        dd = d - timedelta(days=back)
        if dd < EARLIEST:
            break
        mp = _map_path(dd)
        if mp.exists():
            try:
                return json.loads(mp.read_text())
            except ValueError:
                pass  # cache corrompido → re-extrai
        ap = _download(dd)
        if ap is None:
            continue
        try:
            m = _extract_cat3_map(ap)
        except RuntimeError:        # py7zr ausente — não adianta tentar outro dia
            return None
        if m:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            mp.write_text(json.dumps(m))
            return m
    return None


# --------------------------------------------------------------------------- #
# Tendência
# --------------------------------------------------------------------------- #
def build_price_maps(today: date,
                     windows: tuple[int, ...] = DEFAULT_WINDOWS,
                     log: Callable[[str], None] = lambda _s: None
                     ) -> dict[int, dict[str, float]]:
    """{janela: {productId: preço}} pros pontos de referência disponíveis."""
    maps: dict[int, dict[str, float]] = {}
    for w, d in target_dates(today, windows).items():
        m = price_map_for_date(d)
        if m:
            maps[w] = m
            log(f"  histórico {HORIZON_LABELS.get(w, f'{w}d')} "
                f"({d.isoformat()}): {len(m)} preços")
        else:
            log(f"  histórico {HORIZON_LABELS.get(w, f'{w}d')} "
                f"({d.isoformat()}): indisponível")
    return maps


def _label(pct: Optional[float], horizon: str) -> str:
    if pct is None:
        return "n/d"
    arrow = "↑" if pct > THRESHOLD_PCT else "↓" if pct < -THRESHOLD_PCT else "→"
    return f"{arrow} {pct:+.0f}% ({horizon})"


def trend_for(product_id: str, today_price: float,
              maps: dict[int, dict[str, float]],
              windows: tuple[int, ...] = DEFAULT_WINDOWS) -> Trend:
    """Tendência real: hoje vs. o ponto histórico mais distante disponível.

    Usa a MAIOR janela com preço pra esse `productId` como headline (o outlook
    é de longo prazo) e, se houver ~90d, calcula também o momentum recente.
    """
    if not maps:
        return Trend("n/d (sem histórico)")
    avail = [w for w in sorted(windows, reverse=True)
             if w in maps and product_id in maps[w] and maps[w][product_id] > 0]
    if not avail:
        return Trend("n/d (sem histórico)")
    w_long = avail[0]
    old = maps[w_long][product_id]
    pct_long = (today_price - old) / old * 100.0
    pct_recent = None
    if 90 in maps and maps[90].get(product_id, 0.0) > 0:
        o90 = maps[90][product_id]
        pct_recent = (today_price - o90) / o90 * 100.0
    horizon = HORIZON_LABELS.get(w_long, f"{w_long}d")
    return Trend(_label(pct_long, horizon), pct_long, horizon, pct_recent)
