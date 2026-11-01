# matching.py — K96 (Phase 2 · spec 4.2): matcher MOJA kwa bookie.py + betway.py
# Kanuni: kamwe USI-BASHIRI. Shak → REJECT (None) au REJECT kama ambiguous.
from __future__ import annotations
import unicodedata, re, json
from difflib import SequenceMatcher
from pathlib import Path

# tokens za jumla zisizo-viewed: hazisaidii ku-tambua timu
GENERIC_DROP = {"fc", "afc", "cf", "if", "sk", "fk", "club", "teams", "de",
                "ac", "as", "rc", "rb", "rcd", "rfc", "ssc", "bsc", "usd", "ud",
                "cd", "sa", "sv", "svr"}
# tokens ZINAZOTOFAUTISHA timu: ikikosekana upande mmoja → score 0 (spec I)
DISTINGUISHING = {"w", "women", "ladies", "b", "ii", "iii", "reserves",
                  "miami", "city", "united", "sc",
                  *{f"u{n}" for n in range(15, 24)}}

_ALIAS_PATH = Path(__file__).resolve().parent / "data" / "aliases.json"
_ALIASES: dict[str, int] = {}      # alias_fonted → group id
if _ALIAS_PATH.exists():
    try:
        _grp = json.loads(_ALIAS_PATH.read_text(encoding="utf-8")).get("groups", [])
        for i, g in enumerate(_grp):
            for a in g:
                _ALIASES[a.strip().lower()] = i
    except Exception:
        _ALIASES = {}


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("&", " ").replace("+", " ").replace("'", " ").replace(".", " ").replace("-", " ")
    # tennis "Lastname, Firstname" → "firstname lastname"
    if "," in s:
        parts = [x.strip() for x in s.split(",") if x.strip()]
        if len(parts) == 2:
            s = f"{parts[1]} {parts[0]}"
    return re.sub(r"\s+", " ", s).strip()


def _tokens(n: str) -> list[str]:
    return [t for t in normalize(n).split() if t not in GENERIC_DROP]


def _alias_gid(n: str):
    full = normalize(n)
    if full in _ALIASES:
        return _ALIASES[full]
    # jaribu bila tokens za generic
    bare = " ".join(_tokens(n))
    return _ALIASES.get(bare)


def _tok_eq(a: str, b: str) -> bool:
    if a == b:
        return True
    if len(a) == 1 and b.startswith(a):          # initial: "y" ~ "yannick" (tennis)
        return True
    if len(b) == 1 and a.startswith(b):
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.88


def team_sim(a: str, b: str) -> float:
    """0..1 — ulinganisho mwedve wa jina la timu (spec 4.2.2–3)."""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    ga, gb = _alias_gid(a), _alias_gid(b)
    if ga is not None and ga == gb:
        return 1.0
    if na == nb:
        return 1.0
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    da, db = set(ta) & DISTINGUISHING, set(tb) & DISTINGUISHING
    if da != db and na != nb:
        return 0.0                                   # tofauti za maana zinagoma
    # bipartite-greedy ya tokens (soft equality)
    used = set()
    tot = 0.0
    for x in ta:
        best, bi = 0.0, -1
        for j, y in enumerate(tb):
            if j in used:
                continue
            sc = 1.0 if _tok_eq(x, y) else SequenceMatcher(None, x, y).ratio()
            if sc > best:
                best, bi = sc, j
        if bi >= 0 and best >= 0.55:
            used.add(bi)
            tot += best
    jac = (2 * tot) / (len(ta) + len(tb)) if (ta and tb) else 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    # tokens kamili zilikalingana (mf. tennis surname+initial) → acha jaccard iongoshe
    return max(0.55 * jac + 0.45 * seq, jac if jac >= 0.95 else 0.0, 0.0 if jac == 0 else 0.55 * jac + 0.45 * seq)


def _min_hhmm(t: str):
    if not t:
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})", t.strip())
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def event_score(ev_home: str, ev_away: str, home: str, away: str,
                ev_time: str | None, fb_time: str | None) -> tuple[float, bool, str]:
    """Rudi (score, flipped, reason). score < 0.80 → tupu (spec 4.2.3/4.2.4)."""
    sh, sa = team_sim(ev_home, home), team_sim(ev_away, away)
    sc_direct = 0.6 * min(sh, sa) + 0.4 * (sh + sa) / 2 if min(sh, sa) >= 0.80 else 0.0
    sh2, sa2 = team_sim(ev_home, away), team_sim(ev_away, home)
    sc_flip = 0.6 * min(sh2, sa2) + 0.4 * (sh2 + sa2) / 2 if min(sh2, sa2) >= 0.80 else 0.0
    sc, flip = (sc_direct, False) if sc_direct >= sc_flip else (sc_flip, True)
    if sc <= 0:
        return 0.0, False, "names"

    te, tf = _min_hhmm(ev_time or ""), _min_hhmm(fb_time or "")
    if te is not None and tf is not None:
        diff = abs(te - tf)
        if diff > 780:
            diff = 1440 - diff                              # tanda ya usiku (23:55 → 00:05)
        if diff > 20:
            return 0.0, False, f"time diff {diff} min"
    elif sc < 0.92:                                          # hakuna time → ni-pessimistic (4.2.4)
        return 0.0, False, "no time + weak names"
    return sc, flip, ""


def find_event(events: list[dict], sport: str, home: str, away: str,
               time_eat: str | None = None, league: str | None = None,
               log=None):
    """Rudi (event, flipped, score, reason). 'ambiguous' ikifika → (None, False, 0, 'ambiguous')."""
    cands = []
    for e in events:
        if e.get("sport") != sport:
            continue
        lg_e = e.get("league") or e.get("competition") or ""
        sc, flip, why = event_score(e.get("home", ""), e.get("away", ""), home, away,
                                    e.get("time_eat"), time_eat)
        if sc <= 0:
            continue
        lg_bonus = 0.0
        if league and lg_e:
            lt = set(_tokens(league)) | set(normalize(league).split())
            et = set(_tokens(lg_e)) | set(normalize(lg_e).split())
            if lt and et:
                lg_bonus = len(lt & et) / max(len(lt | et), 1) * 0.03
        cands.append((sc + lg_bonus, flip, e))
    if not cands:
        return None, False, 0.0, "hakuna"
    # 4.2.5: HIGHLIGHTS mara nyingi huza fixture SAWA ids mbili → dedupe kabla ya ambiguity
    cands.sort(key=lambda x: -x[0])
    seen_fx = {}
    unq = []
    for sc, flip, e in cands:
        fx = (normalize(e.get("home", "")), normalize(e.get("away", "")))
        if fx not in seen_fx:
            seen_fx[fx] = (sc, flip, e)
            unq.append((sc, flip, e))
    if len(unq) > 1 and unq[0][0] - unq[1][0] <= 0.03:
        if log:
            log(f"  [matching] AMBIGUOUS: {unq[0][2].get('home')} (−{unq[0][0]:.2f}) "
                f"vs {unq[1][2].get('home')} (−{unq[1][0]:.2f}) — REJECT")
        return None, False, 0.0, "ambiguous"
    sc, flip, ev = unq[0]
    return ev, flip, sc, ""
