"""bookies/base.py — muundo wa pamoja wa masoko ya bookmaker na hesabu za bei.

Kila bookmaker anarudisha `Offer` zilizo sawa. Hii inaruhusu kuongeza
bookmaker mpya kwa kuandika faili moja tu.
"""
from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable


class BookieError(RuntimeError):
    """API ya bookmaker haifikiki / kosa la mtandao. HII SI 'hakuna odds'."""


@dataclass
class Offer:
    """Chaguo moja la soko moja kwa bookmaker mmoja."""
    bookmaker: str
    market: str                 # jina la bookmaker (halisi, halibadilishwi)
    market_name: str
    outcome: str
    odds: float | None
    line: float | None = None
    suspended: bool = False
    event_id: str = ""
    retrieved_at: str = ""
    source_url: str = ""
    display_name: str = ""          # jina la kuonyeshwa la bookmaker (kama "Over/Under | Full Time")
    bookmaker_prob: float | None = None   # nambari ya bookmaker mwenyewe (TAARIFA tu;
                                          # injini hutumia devig kutoka odds, si nambari hii)

    @property
    def usable(self) -> bool:
        return (self.odds is not None and not self.suspended
                and isinstance(self.odds, (int, float)) and 1.01 <= float(self.odds) <= 300)


@dataclass
class BookieDay:
    events: list[dict] = field(default_factory=list)
    retrieved_at: str = ""
    source_url: str = ""
    error: str = ""
    ok: bool = True


# ---------------------------------------------------------------- HTTP ya JSON
def json_get(url: str, headers: dict, timeout: int = 25, tries: int = 2,
             min_interval_s: float = 0.4) -> dict:
    """Ombi la JSON lenye retries zenye mipaka. Hairudishi kimya kimya."""
    err = None
    for i in range(max(1, tries)):
        if min_interval_s > 0:
            time.sleep(min_interval_s)
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            err = e
            if i + 1 < tries:
                time.sleep(1.0 + i)
    raise BookieError(f"{type(err).__name__}: {str(err)[:160]}")


# ------------------------------------------------------------------ DEVIG ----
def devig(odds: list, total: float = 1.0) -> list[float | None]:
    """Ondoa margin ya bookmaker: p_i = (1/o_i) / Σ(1/o_j), kisha zidisha kwa `total`.

    Kwa Double Chance (matokeo 3 ambapo matokeo mawili yanaweza kutokea pamoja)
    jumla ni 2, si 1 — tumia `total=2.0`.
    """
    inv = []
    for o in odds:
        try:
            v = float(o)
        except (TypeError, ValueError):
            return [None] * len(odds)
        if v < 1.01:
            return [None] * len(odds)
        inv.append(1.0 / v)
    s = sum(inv)
    if s <= 0:
        return [None] * len(odds)
    return [round(x / s * total, 6) for x in inv]


def overround(odds: list) -> float | None:
    inv = []
    for o in odds:
        try:
            v = float(o)
        except (TypeError, ValueError):
            return None
        if v < 1.01:
            return None
        inv.append(1.0 / v)
    return round(sum(inv) - 1.0, 6) if inv else None


def combine_probs(entries: list[tuple[list[float | None], float]]) -> list[float | None]:
    """Changanya uwezekano kutoka bookmaker kadhaa kwa uzito.

    `entries` = [(probs_list, weight), ...]
    """
    entries = [(p, w) for p, w in entries if p and w > 0]
    if not entries:
        return []
    n = max(len(p) for p, _ in entries)
    out: list[float | None] = []
    for i in range(n):
        num = den = 0.0
        for p, w in entries:
            if i < len(p) and p[i] is not None:
                num += p[i] * w
                den += w
        out.append(round(num / den, 6) if den > 0 else None)
    return out


def disagree(probs_by_bookie: list[list[float | None]], index: int,
             thresh: float = 0.06) -> bool:
    vals = [p[index] for p in probs_by_bookie if p and index < len(p) and p[index] is not None]
    if len(vals) < 2:
        return False
    return (max(vals) - min(vals)) > thresh


# ------------------------------------------------------- circuit breaker ----
class Breaker:
    """Zuia bookmaker aliyekufa kujaribiwa kila mechi (mara 5 mfululizo → off)."""

    def __init__(self, fail_limit: int = 5, budget_s: float = 480.0):
        self.fail_limit = fail_limit
        self.budget_s = budget_s
        self.failures = 0
        self.open_until_end = False
        self.started = time.monotonic()
        self.requests = 0

    def allow(self) -> bool:
        if self.open_until_end:
            return False
        if self.budget_s and (time.monotonic() - self.started) > self.budget_s:
            return False
        return True

    def ok(self) -> None:
        self.failures = 0

    def fail(self) -> None:
        self.failures += 1
        if self.failures >= self.fail_limit:
            self.open_until_end = True

    def tick(self) -> None:
        self.requests += 1
