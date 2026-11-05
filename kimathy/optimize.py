"""optimize.py — kiboreshaji cha accumulator (Sehemu 12).

Lengo: combined decimal odds ndani ya [1.80, 2.00] **pamoja na mipaka hiyo**.
Idadi ya miguu INABADILIKA. Kamwe miguu miwili kutoka mechi moja.
DP juu ya mabaketi ya log-odds — deterministic, hakuna nasibu.

Kama hakuna mchanganyiko unaopita: `NO QUALIFIED ACCUMULATOR` + sababu.
HATULAZIMISHI dau dhaifu ili kufikia 1.80.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

STEP = 0.005
MAX_BUCKETS = 1200


@dataclass
class Accumulator:
    legs: list[dict]
    total_odds: float
    joint_prob: float
    risk: float
    ev: float
    correlation_pairs: int = 0
    status: str = "QUALIFIED ACCUMULATOR"
    reasons: list[str] = field(default_factory=list)
    label: str = "ACCUMULATOR"

    def legs_count(self) -> int:
        return len(self.legs)


def _corr_pairs(legs: list[dict]) -> int:
    n = 0
    for i in range(len(legs)):
        for j in range(i + 1, len(legs)):
            a, b = legs[i].get("league", ""), legs[j].get("league", "")
            if a and a == b:
                n += 1
    return n


def joint_probability(legs: list[dict], haircut: float = 0.98) -> tuple[float, int]:
    """Πp × haircut^(pairs zenye correlation). Uhuru HAUDHANIWI bila tahadhari."""
    p = 1.0
    for l in legs:
        p *= max(float(l.get("p_engine", 0.0)), 1e-6)
    pairs = _corr_pairs(legs)
    return round(p * (haircut ** pairs), 6), pairs


def build(candidates: list[dict], cfg, log=print) -> tuple[Accumulator | None, list[str]]:
    """Tafuta accumulator bora. Rudia (Accumulator|None, sababu_za_kukataa)."""
    acc = cfg.section("accumulator")
    o_min = float(acc.get("combined_odds_min", 1.80))
    o_max = float(acc.get("combined_odds_max", 2.00))
    max_legs = int(acc.get("max_legs", 12))
    force = acc.get("force_legs")
    haircut = float(acc.get("correlation_haircut", 0.98))

    reasons: list[str] = []
    legs = []
    seen_matches = set()
    for c in sorted(candidates, key=lambda x: (-float(x.get("p_engine", 0)),
                                              -float(x.get("odds", 0)))):
        mk = (c.get("home", ""), c.get("away", ""))
        if mk in seen_matches:            # sheria: mgombea mmoja kwa mechi
            continue
        if not c.get("odds") or not c.get("p_engine"):
            continue
        if float(c["odds"]) <= 1.0:
            continue
        seen_matches.add(mk)
        legs.append(c)
    legs = legs[:60]

    if not legs:
        reasons.append("hakuna mgombea yeyote aliye na bei halisi ya bookmaker")
        return None, reasons

    ln_min, ln_max = math.log(o_min), math.log(o_max)
    # DP juu ya mabaketi ya log-odds. Kila hali hubakiza alama bora, lakini pia
    # tunakusanya kila njia ambayo odds yake HALISI iko ndani ya safu — ili baketi
    # isiweze kupoteza mchanganyiko halali (bug iliyogunduliwa kwenye majaribio).
    states: dict[tuple[int, int], tuple[float, float, tuple]] = {(0, 0): (0.0, 0.0, ())}
    good: dict[tuple, tuple[float, float]] = {}
    for i, leg in enumerate(legs):
        lo = math.log(float(leg["odds"]))
        lp = math.log(max(float(leg["p_engine"]), 1e-6))
        for (b, c), (sc, sl, path) in list(states.items()):
            if c >= max_legs:
                continue
            nb, nc = b + int(round(lo / STEP)), c + 1
            if nb > MAX_BUCKETS:
                continue
            nsc, nsl = sc + lp, sl + lo
            npath = path + (i,)
            if ln_min - 1e-9 <= nsl <= ln_max + 1e-9:
                cur_good = good.get(npath)
                if cur_good is None or nsc > cur_good[0]:
                    good[npath] = (nsc, nsl)
            cur = states.get((nb, nc))
            if cur is None or nsc > cur[0]:
                states[(nb, nc)] = (nsc, nsl, npath)

    cands: list[tuple[float, list[dict]]] = []
    seen_paths = set()
    for path, (sc, sl) in good.items():
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        cands.append((sc, [legs[i] for i in path]))
    for (b, c), (sc, sl, path) in states.items():
        if c == 0 or not path or path in seen_paths:
            continue
        if not (ln_min - 1e-9 <= sl <= ln_max + 1e-9):
            continue
        seen_paths.add(path)
        cands.append((sc, [legs[i] for i in path]))

    if not cands:
        odds_all = [round(float(l["odds"]), 2) for l in legs[:12]]
        reasons.append(f"hakuna mchanganyiko wa odds ndani ya {o_min}–{o_max}")
        reasons.append(f"odds za wagombea: {odds_all}")
        reasons.append(f"wagombea waliopatikana: {len(legs)}")
        return None, reasons

    cands.sort(key=lambda x: -x[0])
    best_sc, best_legs = cands[0]
    total = 1.0
    for l in best_legs:
        total *= float(l["odds"])
    total = round(total, 3)
    jp, pairs = joint_probability(best_legs, haircut)

    if not (o_min - 1e-9 <= total <= o_max + 1e-9):
        reasons.append(f"odds ya jumla {total} iko nje ya {o_min}–{o_max}")
        return None, reasons

    acc_out = Accumulator(
        legs=best_legs, total_odds=total, joint_prob=jp, risk=round(1 - jp, 6),
        ev=round(jp * total - 1.0, 4), correlation_pairs=pairs,
        status="QUALIFIED ACCUMULATOR",
        reasons=_explain(best_legs, cands, o_min, o_max, total, jp, pairs),
    )
    log(f"  ✓ ACCUMULATOR: miguu {len(best_legs)} · odds {total} · "
        f"uwezekano wa pamoja {jp:.1%} · EV {acc_out.ev:+.3f}")
    return acc_out, reasons


def _explain(legs, cands, o_min, o_max, total, jp, pairs) -> list[str]:
    alt = len(cands) - 1
    r = [f"michanganyiko {len(cands)} ilifikia safu {o_min}–{o_max}; hii ina uwezekano wa juu zaidi",
         f"miguu {len(legs)} · odds ya jumla {total} · uwezekano wa pamoja {jp:.1%} · "
         f"hatari {1 - jp:.1%}"]
    if pairs:
        r.append(f"jozi {pairs} za correlation (ligi moja) zimepunguzwa kwa haircut")
    else:
        r.append("hakuna jozi za correlation zilizogunduliwa (uhuru bado ni DHANA, si ukweli)")
    if alt > 0:
        r.append(f"mbadala {alt} zilikuwepo lakini zina uwezekano mdogo wa pamoja")
    return r


def no_qualified(reasons: list[str], candidates: list[dict], cfg) -> Accumulator:
    acc = cfg.section("accumulator")
    return Accumulator(
        legs=[], total_odds=0.0, joint_prob=0.0, risk=0.0, ev=0.0,
        status="NO QUALIFIED ACCUMULATOR",
        reasons=(reasons or ["hakuna sababu iliyorekodiwa"]) +
                [f"wagombea waliopimwa: {len(candidates)}",
                 f"safu iliyotakiwa: {acc.get('combined_odds_min')}–{acc.get('combined_odds_max')}"],
    )
