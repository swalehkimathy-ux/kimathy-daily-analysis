# oddsx.py — K96 (Phase 3 · spec 5.2): devig + kuunganisha probabilities za bookies
# p_i = (1/o_i) / Σ(1/o_j)  → margin imetolewa (proportional).
# RULES G2: baadhi ya masoko yawezeshwa kuwa "total ya KUSHA" ya 2 (Double Chance:
# Σimplied ≈ 2 km kila combo mbili) — hapo normalize to=2, isivyo 1.
from __future__ import annotations


def devig(odds: list, total: float = 1.0) -> list[float | None]:
    """Rudi probabilities bila-margin moja kwa moja na utaratibu wa odds. None kwa odds mbaya.
    total: probabilities zinajumlisha hii (1.0 markets zisizokusunu; 2.0 kwa Double Chance)."""
    inv = []
    for o in odds:
        try:
            o = float(o)
            inv.append(1.0 / o if o > 1.001 else None)
        except Exception:
            inv.append(None)
    tot = sum(x for x in inv if x)
    if not tot:
        return [None] * len(odds)
    return [None if x is None else x / tot * total for x in inv]


def combine_probs(entries: list[tuple[list[float | None], float]]):
    """Changanya probability vectors kutoka bookies nyingi kwa weights.
    entries: [(probs_list, weight)]. Rudi list (None pale probabilities zote zikikose.)"""
    n = None
    for v, _ in entries:
        if v is not None:
            n = len(v)
            break
    if n is None:
        return []
    out = [None] * n
    for i in range(n):
        acc = 0.0
        den = 0.0
        for v, w in entries:
            if v is None:
                continue
            x = v[i]
            if x is None:
                continue
            acc += x * w
            den += w
        out[i] = (acc / den) if den else None
    return out


def disagree_flag(probs_by_bookie: list[list[float | None]], thresh: float = 0.06) -> list[bool]:
    """Rudi True kwa kila outcome ambapo dispersion > thresh (0.06 = 6 pts) (spec 5.2)."""
    if len(probs_by_bookie) < 2:
        return [False] * (len(probs_by_bookie[0]) if probs_by_bookie else 0)
    n = len(probs_by_bookie[0])
    flags = []
    for i in range(n):
        vals = [v[i] for v in probs_by_bookie if v and v[i] is not None]
        flags.append(bool(vals) and (max(vals) - min(vals)) > thresh)
    return flags
