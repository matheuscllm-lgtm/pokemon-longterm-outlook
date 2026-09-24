"""Censo PSA oficial por carta via GemRate (gemrate.com) — modo low pop.

Por que (2026-09-24): o censo embutido no PriceCharting (`VGPC.pop_data`) é
uma foto mensal que atrasa MESES em set moderno. N's Zoroark ex #286 (Ascended
Heroes) saía com 1.046 PSA 10 quando o Pop Report da PSA já tinha 3.318 (3,2×);
Sylveon V #184 (Evolving Skies) com 1/6 quando o real era 7.163/13.906. A
Escassez do score ficava inflada exatamente nas cartas que mais importam.

O Pop Report da PSA exige login e a API pública responde "limited to approved
customers" (403). A GemRate publica o pop da PSA por carta, sem login, com
atualização diária, e o número bate com o oficial (conferido no eBay/PSA).

O que usamos: a página por Pokémon (`/player?grader=psa&player=<nome>`), que
embute `var RowData = JSON.parse('[...]')` com UM registro por (set, número,
paralelo): `gems` = nº de PSA 10, `psa_9_plus`, `total`, `year`, `set_name`,
`name`, `parallel`. Uma página cobre a carta em TODOS os sets — inclusive
vintage (Espeon H9 Aquapolis) — e em todos os idiomas (só o inglês entra).

Como a GemRate escreve (sonda 2026-09-24, nomes REAIS):
  - vintage: "Pokemon Game" (= Base Set), "Pokemon Game Base II", "Pokemon
    Jungle", "Pokemon Neo Genesis 1st Edition" (set SEPARADO), "Pokemon EX Fire
    Red & Leaf Green" (catálogo: "EX FireRed & LeafGreen"); variante no nome
    ("Espeon-Holo", "Gardevoir-Reverse Foil") ou no paralelo ("Holo",
    "1st Edition", "Shadowless"); idiomas e theme decks no paralelo.
  - DP → SWSH: "Pokemon Diamond & Pearl Secret Wonders", "Pokemon Black & White
    Dark Explorers", "Pokemon Sword & Shield Evolving Skies" (era no nome);
    alt art como "Full Art/Sylveon V" com paralelo "Base".
  - SV/ME: "Pokemon <Cod> EN-<Set>" ("Pokemon Mew EN-151", "Pokemon Asc
    EN-Ascended Heroes"); o paralelo é a RARIDADE ("Special Illustration
    Rare", "Shiny Rare") ou "Base"; outros idiomas viram set próprio
    ("Pokemon Italian Mew It-151").

Precisão > cobertura (regra da frota): o registro só é aceito quando número,
ANO de lançamento, set (tokens sem era/ruído) e nome batem, o paralelo é
"Base"/"Holo"/a raridade do catálogo e a variante (holo / reverse / 1st /
shadowless / theme deck) é a que o catálogo pede. Ambiguidade → None, e a
carta cai no PriceCharting, declarado.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from .psa10 import _number_forms, _token_list

BASE = "https://www.gemrate.com"
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache" / "gemrate"
CACHE_TTL_DAYS = 7      # o censo muda todo dia, mas a semana basta pro score
SLEEP_S = 1.5           # educado com o site
TIMEOUT_S = 30

# Palavras que não distinguem set: era (vêm no nome da GemRate, não no do
# catálogo, que as traz como prefixo "SWSH07:") e ruído de catálogo.
_NOISE = {"pokemon", "tcg", "and", "the", "of", "base", "set", "en", "asc"}
_ERA = {"sword", "shield", "scarlet", "violet", "sun", "moon", "xy", "black",
        "white", "diamond", "pearl", "platinum", "heartgold", "soulsilver",
        "swsh", "sv", "sm", "bw", "dp", "hgss", "ex", "me"}
# Sigla de era do catálogo → palavras que a GemRate usa ("SM Base Set" ↔
# "Pokemon Sun & Moon"); só entra na comparação de set "só de era".
_ERA_ALIAS = {"sm": ("sun", "moon"), "swsh": ("sword", "shield"), "bw": ("black", "white"),
              "dp": ("diamond", "pearl"), "hgss": ("heartgold", "soulsilver"),
              "sv": ("scarlet", "violet")}
_ERA_PREFIX_RE = re.compile(r"^[A-Z]{2,4}\d{0,2}\s*[:\-–]\s*")   # "SWSH07: ", "XY - ", "ME: "
# Subconjunto que o catálogo lista como set próprio e a GemRate dobra no set
# principal (mesma numeração TG##/GG##/SV##): "Hidden Fates: Shiny Vault",
# "SWSH11: Lost Origin Trainer Gallery", "SWSH: Crown Zenith: Galarian Gallery".
_SUBSET_SUFFIX_RE = re.compile(r":?\s*\b(shiny vault|trainer gallery|galarian gallery)\s*$", re.I)
_CATALOG_NUM_QUIRK_RE = re.compile(r"\s+-\s*\d+/\d+")            # "Mimikyu -160/091", "Ditto - 039/113 (…)"
# Set moderno inglês: "Pokemon Mew EN-151" → "151". Outros idiomas têm a língua
# no nome ("Pokemon Italian Mew It-151") e são recusados.
_EN_CODE_RE = re.compile(r"^\s*pokemon\s+\w+\s+EN-(.+)$", re.I)
_LANG_RE = re.compile(r"\b(italian|french|german|spanish|latin american|japanese|"
                      r"portuguese|chinese|korean|indonesian|thai|russian|dutch|"
                      r"polish|traditional|simplified)\b", re.I)
# Nomes de set do catálogo (tcgcsv) que a PSA/GemRate chama de outro jeito.
_SET_OVERRIDES = {
    "base set": "game",
    "base set 2": "game base ii",
    "team rocket": "rocket",
}
# Tokens de paralelo que NÃO mudam a carta (o resto é idioma/promo/theme deck).
_NEUTRAL_PARALLEL = {"base", "holo"}
# Rótulo de raridade que a GemRate põe no paralelo e que NÃO bate palavra a
# palavra com o catálogo: XY chama a secret rare de "Ultra Rare"; SM chama a
# rainbow/hyper rare de "Secret". Só entra pra ESSAS raridades do catálogo —
# em SV/ME o paralelo é a raridade exata e continua exigido igual.
_RARITY_PARALLEL_SYNONYMS = {
    "secret": {"ultra", "rare", "secret"},
    "rainbow": {"secret", "rare"},
    "hyper": {"secret", "rare"},
}
# Raridade do catálogo em que a carta PODE ser não-holo: só aqui a regra
# "holo ↔ -Holo" é estrita (achado da revisão de 2026-09-24). Toda outra
# raridade (Ultra/Secret/Rainbow/Shiny Holo/Amazing…) é sempre foil e a
# GemRate a nomeia "-Holo" em EX/DP/PL/HGSS/BW ("Umbreon-Holo" = Prime #86,
# "Charizard EX-Holo" = ex #105) — exigir "holo" na raridade derrubava 118
# cartas do run de 2026-09-24 sem ganhar precisão nenhuma.
_PLAIN_RARITIES = {"common", "uncommon", "rare", "promo"}
# "Shiny Holo Rare" (SV## do Shiny Vault) tem "holo" no rótulo mas não é essa
# distinção — a GemRate lista "Full Art/Umbreon GX | Base"; cai no caso
# sempre-foil (só "Holo Rare" estrito exige o registro "-Holo").
# Variantes de impressão: só entram quando o set do catálogo as pede.
_PRINT_VARIANTS = {"1st", "edition", "shadowless", "reverse", "foil"}


@dataclass(frozen=True)
class GemratePop:
    pop10: int          # nº de PSA 10 (o dado que importa)
    psa9_plus: int      # PSA 9 + PSA 10
    total: int          # todas as notas
    record: dict        # registro bruto da GemRate (auditoria)


# ── Parsers (puros, testados offline) ────────────────────────────────────────

def _js_string_literal(html: str, marker: str) -> str | None:
    """Conteúdo da string JS entre aspas simples que segue `marker`."""
    i = html.find(marker)
    if i < 0:
        return None
    i += len(marker)
    j = i
    while True:
        j = html.find("'", j)
        if j < 0:
            return None
        k = j
        while k > i and html[k - 1] == "\\":
            k -= 1
        if (j - k) % 2 == 0:          # nº par de barras = aspa NÃO escapada
            return html[i:j]
        j += 1


def parse_player_page(html: str) -> list[dict]:
    """Registros de `var RowData = JSON.parse('[...]')`, ou [] se não há."""
    lit = _js_string_literal(html, "RowData = JSON.parse('")
    if lit is None:
        return []
    try:
        data = json.loads(lit.replace("\\'", "'"))
    except ValueError:
        return []
    return [d for d in data if isinstance(d, dict)]


def parse_sets_index(html: str) -> list[dict]:
    """Sets Pokémon de `let setsData = [...]` (índice /universal-pop-report)."""
    i = html.find("setsData = [")
    if i < 0:
        return []
    i = html.index("[", i)
    depth, j = 0, i
    while j < len(html):
        depth += (html[j] == "[") - (html[j] == "]")
        j += 1
        if depth == 0:
            break
    try:
        data = json.loads(html[i:j])
    except ValueError:
        return []
    return [d for d in data if isinstance(d, dict) and "pokemon" in str(d.get("set_name", "")).lower()]


# ── Match registro ↔ carta ───────────────────────────────────────────────────

def player_query(card_name: str) -> str:
    """Nome que a GemRate entende como "player": o nome do catálogo sem o
    qualificador entre parênteses e sem o quirk "-160/091" do TCGPlayer."""
    name = _CATALOG_NUM_QUIRK_RE.sub("", card_name or "")
    out, depth = [], 0
    for ch in name:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return " ".join("".join(out).split())


def _num_key(number: str) -> str:
    """Grafia canônica do número: sem denominador, sem zeros à esquerda e sem o
    zero depois da letra (H09 → H9), em minúsculas."""
    return _number_forms(str(number or ""))[-1].lower()


def _core(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in _NOISE and t not in _ERA]


def _catalog_set_core(set_name: str) -> list[str]:
    name = _ERA_PREFIX_RE.sub("", set_name or "")
    name = _SUBSET_SUFFIX_RE.sub("", name)
    name = re.sub(r"\(.*?\)", " ", name)
    key = " ".join(name.lower().split())
    if key in _SET_OVERRIDES:
        name = _SET_OVERRIDES[key]
    return _core(_token_list(name))


def _gemrate_set_core(set_name: str) -> list[str] | None:
    """Tokens do set da GemRate, ou None se não é a edição em inglês."""
    if _LANG_RE.search(set_name or ""):
        return None
    m = _EN_CODE_RE.match(set_name or "")
    name = m.group(1) if m else set_name
    return _core(_token_list(name))


def _era_tokens(name: str) -> set[str]:
    out: set[str] = set()
    for t in _token_list(name):
        if t in _ERA:
            out.update(_ERA_ALIAS.get(t, (t,)))
    return out


def _set_matches(catalog_set: str, gemrate_set: str) -> bool:
    a, b = _catalog_set_core(catalog_set), _gemrate_set_core(gemrate_set)
    if b is None:
        return False
    if not a and not b:
        # Set que se chama só pela era ("Sword & Shield", "XY"): o núcleo fica
        # vazio dos dois lados e [] == [] não prova nada (achado da revisão) —
        # aí as palavras de era têm que ser as mesmas.
        cat = _ERA_PREFIX_RE.sub("", catalog_set or "")
        m = _EN_CODE_RE.match(gemrate_set or "")
        return _era_tokens(cat) == _era_tokens(m.group(1) if m else gemrate_set)
    # "fire-red & leaf-green" ↔ "FireRed & LeafGreen": a sequência colada
    # também vale (mesma regra do guard do PriceCharting).
    return a == b or "".join(a) == "".join(b)


def match_record(records: list[dict], card_name: str, set_name: str, number: str,
                 release_year: int, rarity: str) -> GemratePop | None:
    """O registro da GemRate que É esta carta, ou None (ambíguo/ausente)."""
    want_num = _num_key(number)
    want_name = set(_token_list(player_query(card_name)))
    rarity_tokens = set(_token_list(rarity or ""))
    qualifier = set(_token_list(" ".join(re.findall(r"\((.*?)\)", set_name))))
    allowed_parallel = _NEUTRAL_PARALLEL | rarity_tokens | qualifier
    for tok in rarity_tokens & _RARITY_PARALLEL_SYNONYMS.keys():
        allowed_parallel |= _RARITY_PARALLEL_SYNONYMS[tok]
    cands = []
    for r in records:
        if str(r.get("year", "")).strip() != str(release_year):
            continue
        if _num_key(str(r.get("card_number", ""))) != want_num:
            continue
        if not _set_matches(set_name, str(r.get("set_name", ""))):
            continue
        name_tokens = set(_token_list(str(r.get("name", ""))))
        if not want_name <= name_tokens:
            continue
        par_tokens = set(_token_list(str(r.get("parallel", ""))))
        if not par_tokens <= allowed_parallel:
            continue   # idioma, theme deck, promo, tin, 1st edition não pedida…
        variant = (name_tokens | par_tokens) & _PRINT_VARIANTS
        if variant - qualifier - rarity_tokens:
            continue   # reverse/1st/shadowless que o catálogo não pediu
        if qualifier and not qualifier <= (name_tokens | par_tokens):
            continue   # "Base Set (Shadowless)": o registro tem que dizer shadowless
        cands.append(r)

    def is_holo(r):
        return "holo" in (set(_token_list(str(r.get("name", ""))))
                          | set(_token_list(str(r.get("parallel", "")))))
    # A variante holo tem que ser a que a raridade do catálogo pede — sem
    # fallback: "Rare" com só o registro "-Holo" sobrando é OUTRA impressão
    # (achado da revisão de 2026-09-24), e o inverso também.
    if "holo" in rarity_tokens and rarity_tokens <= {"holo", "rare"}:
        cands = [r for r in cands if is_holo(r)]   # "Holo Rare": só a holo
    elif rarity_tokens <= _PLAIN_RARITIES:
        cands = [r for r in cands if not is_holo(r)]
    # Raridade sempre-foil (Ultra/Secret/Rainbow/…): "-Holo" é só o nome que
    # a GemRate dá à impressão única — não filtra.
    if len(cands) != 1:
        return None
    r = cands[0]
    try:
        return GemratePop(pop10=int(r.get("gems") or 0), psa9_plus=int(r.get("psa_9_plus") or 0),
                          total=int(r.get("total") or 0), record=r)
    except (TypeError, ValueError):
        return None


# ── Rede + cache ─────────────────────────────────────────────────────────────

_session = None


def _get(url: str) -> str:
    """HTML da URL numa sessão com TLS de Chrome (curl_cffi); lança em falha."""
    global _session
    if _session is None:
        from curl_cffi import requests as cr  # local: módulo importável sem a lib
        _session = cr.Session(impersonate="chrome")
    r = _session.get(url, timeout=TIMEOUT_S)
    time.sleep(SLEEP_S)
    if r.status_code != 200:
        raise OSError(f"HTTP {r.status_code}")
    return r.text


def _cache_path(kind: str, key: str) -> Path:
    return CACHE_DIR / f"{kind}_{hashlib.sha1(key.encode('utf-8')).hexdigest()}.json"


def fetch_player(player: str, use_cache: bool = True) -> list[dict]:
    """Registros da página por Pokémon (cache de CACHE_TTL_DAYS)."""
    p = _cache_path("player", player.lower())
    if use_cache and p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            age = (date.today() - date.fromisoformat(d["_cached_on"])).days
            if age <= CACHE_TTL_DAYS:
                return d["records"]
        except (ValueError, KeyError, OSError):
            pass
    url = f"{BASE}/player?" + urlencode({"grader": "psa", "player": player})
    records = parse_player_page(_get(url))
    if use_cache:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"_cached_on": date.today().isoformat(), "player": player,
                                     "records": records}), encoding="utf-8")
        except OSError:
            pass
    return records


def lookup(card_name: str, set_name: str, number: str, release_year: int,
           rarity: str, use_cache: bool = True) -> GemratePop | None:
    """Pop PSA da carta, ou None — nunca inventa (rede caiu = None)."""
    try:
        records = fetch_player(player_query(card_name), use_cache=use_cache)
    except Exception:
        return None
    return match_record(records, card_name, set_name, number, release_year, rarity)
