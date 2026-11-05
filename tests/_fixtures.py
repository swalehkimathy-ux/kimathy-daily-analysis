"""_fixtures.py — data bandia ya majaribio (OFFLINE kabisa, hakuna mtandao).

Hii HAISI injini: ni chanzo cha data cha majaribio. Injini yenyewe inatumia
moduli halisi za kimathy.* — hakuna logic inayorudiwa hapa.
"""
from __future__ import annotations

import datetime as _dt

from kimathy import clock
from kimathy.bookies.base import Offer


def kickoff_in(hours: float, minutes: int = 0) -> _dt.datetime:
    return clock.now_tz() + _dt.timedelta(hours=hours, minutes=minutes)


def rec(home, away, p1, px, p2, avg=None, ps=None, league="Ligi Kuu", sport="football",
        hours=3, status="Scheduled", **kw):
    r = {
        "event_id": f"forebet:test-{home}-{away}".lower().replace(" ", ""),
        "sport": sport, "league": league, "home": home, "away": away,
        "kickoff_tz": kickoff_in(hours), "status": status,
        "probs": {"1": p1, "X": px, "2": p2},
        "predicted_score": ps, "avg": avg, "odds_1x2": None,
        "home_form": kw.get("home_form", []), "away_form": kw.get("away_form", []),
        "avg_h": kw.get("avg_h"), "avg_a": kw.get("avg_a"), "best_of": kw.get("best_of"),
        "source": "forebet",
        "source_url": f"https://www.forebet.com/en/football/matches/{home}-{away}-1",
        "retrieved_at": clock.now_tz().isoformat(timespec="seconds"), "raw": {},
    }
    return r


def _off(market, market_name, outcome, odds, line=None, bookmaker="betpawa", event_id="e1"):
    return Offer(bookmaker=bookmaker, market=market, market_name=market_name,
                 outcome=outcome, odds=odds, line=line, suspended=False,
                 event_id=event_id, retrieved_at=clock.now_tz().isoformat(timespec="seconds"),
                 source_url=f"https://example.test/events/{event_id}")


def football_offers(event_id="e1", bookmaker="betpawa") -> list[Offer]:
    """Masoko ya kawaida ya mpira, kwa majina yanayotumika na bookmaker halisi."""
    o = []
    o += [_off("1X2", "Match Result", "Home", 1.85, bookmaker=bookmaker, event_id=event_id),
          _off("1X2", "Match Result", "Draw", 3.60, bookmaker=bookmaker, event_id=event_id),
          _off("1X2", "Match Result", "Away", 4.40, bookmaker=bookmaker, event_id=event_id)]
    o += [_off("4693", "Double Chance", "1X", 1.22, bookmaker=bookmaker, event_id=event_id),
          _off("4693", "Double Chance", "12", 1.30, bookmaker=bookmaker, event_id=event_id),
          _off("4693", "Double Chance", "X2", 1.95, bookmaker=bookmaker, event_id=event_id)]
    o += [_off("4703", "Draw No Bet", "Home", 1.35, bookmaker=bookmaker, event_id=event_id),
          _off("4703", "Draw No Bet", "Away", 3.10, bookmaker=bookmaker, event_id=event_id)]
    for line in (0.5, 1.5, 2.5, 3.5, 4.5):
        ov = {0.5: 1.02, 1.5: 1.18, 2.5: 1.72, 3.5: 2.60, 4.5: 4.20}[line]
        un = {0.5: 14.0, 1.5: 4.60, 2.5: 2.10, 3.5: 1.46, 4.5: 1.20}[line]
        o.append(_off("5000", "Total Goals", "Over", ov, line=line, bookmaker=bookmaker,
                      event_id=event_id))
        o.append(_off("5000", "Total Goals", "Under", un, line=line, bookmaker=bookmaker,
                      event_id=event_id))
    o += [_off("3795", "Both Teams To Score", "Yes", 1.80, bookmaker=bookmaker, event_id=event_id),
          _off("3795", "Both Teams To Score", "No", 1.98, bookmaker=bookmaker, event_id=event_id)]
    return o


class FixtureProvider:
    """Bookmaker bandia — anafuata muundo ule ule wa Provider halisi."""

    def __init__(self, offers_by_match: dict[str, list[Offer]], day: str | None = None,
                 records: list[dict] | None = None):
        self.offers_by_match = offers_by_match
        self.day = day or clock.today_tz().isoformat()
        self.down: dict[str, str] = {}
        self.calls = 0
        self.records = records or []

    def available(self):
        names = set()
        for v in self.offers_by_match.values():
            names.update(o.bookmaker for o in v)
        return sorted(names)

    def build_index(self):
        return None

    def match_event(self, name, rec):
        return None, False, 0.0, "fixture"

    def discover_markets(self, rec):
        self.calls += 1
        key = f"{rec.get('home','')}|{rec.get('away','')}"
        return list(self.offers_by_match.get(key, [])), "fixture"

    def snapshot(self, name, event_id, flipped=False):
        return []

    def verify(self, rec, market_name, selection, line=None):
        return {"ok": False, "reason": "fixture provider"}

    def select_offer(self, offers, market_name, selection, line=None, flipped=False, rec=None):
        # inatumia njia HALISI ya kimathy.bookies.provider.Provider._select_offer
        from kimathy.bookies.provider import Provider
        return Provider._select_offer(self, offers, market_name, selection, line,
                                      flipped, rec or {})

    def report(self):
        return {"bookmakers_enabled": self.available(), "bookmakers_available": self.available(),
                "bookmakers_down": {}, "index_events": {}, "snapshots": 0,
                "verified_offers": 0, "market_not_offered": 0, "unmatched_events": 0}
