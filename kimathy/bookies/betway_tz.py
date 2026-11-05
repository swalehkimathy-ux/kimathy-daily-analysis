"""bookies/betway_tz.py — Betway Tanzania (chanzo cha ODDS cha msingi).

Njia halisi (zilizothibitishwa kufanya kazi kwenye toleo la awali):
  * Orodha ya siku : /BetBook/Highlights/?countryCode=TZ&sportId=...
  * Masoko ya tukio: /MarketGroupings/MarketGroupNamesAndMarketsForEvent?eventId=...

KUMBUKA: Highlights inaomba `marketTypes=[Win/Draw/Win]` kwa mpira, kwa hiyo
orodha ya siku ni ya 1X2 — lakini endpoint ya masoko ya tukio inarudisha masoko
YOTE. Ugunduzi mpana unategemea betPawa zaidi; Betway inathibitisha bei.
"""
from __future__ import annotations

import datetime as _dt
import urllib.parse

from .. import clock
from .base import BookieDay, BookieError, Offer, json_get

NAME = "betway"
FEEDS = "https://feeds-roa2.betwayafrica.com/br/_apis/sport/v1"
HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KimathyEngine/1.0",
    "Origin": "https://www.betway.co.tz",
    "Referer": "https://www.betway.co.tz/",
    "Accept": "application/json",
}
SPORT_ID = {"football": "soccer", "basketball": "basketball", "tennis": "tennis"}
MAX_SKIP = 300
PAGE = 50


def _get(path_q: str, timeout: int = 25, tries: int = 2) -> dict:
    return json_get(FEEDS + path_q, HDRS, timeout=timeout, tries=tries)


def day_index(day_iso: str, sports: list[str], log=print, timeout: int = 25) -> BookieDay:
    """Matukio yote ya siku (EAT) kwa michezo iliyoruhusiwa."""
    out: list[dict] = []
    for sport, sid in SPORT_ID.items():
        if sport not in sports:
            continue
        skip, kept = 0, 0
        while skip <= MAX_SKIP:
            mt = "[Win/Draw/Win]" if sport == "football" else ""
            q = (f"/BetBook/Highlights/?countryCode=TZ&sportId={sid}&Skip={skip}&Take={PAGE}"
                 f"&cultureCode=en-US&isEsport=false&boostedOnly=false"
                 f"&marketTypes={urllib.parse.quote(mt)}")
            d = _get(q, timeout=timeout)
            evs = d.get("events") or []
            for e in evs:
                ep = e.get("expectedStartEpoch")
                if not ep:
                    continue
                try:
                    eat = _dt.datetime.fromtimestamp(int(ep), _dt.timezone.utc).astimezone(clock.TZ)
                except (ValueError, OSError, OverflowError):
                    continue
                if eat.date().isoformat() != day_iso:
                    continue
                kept += 1
                out.append({"id": str(e["eventId"]), "home": e.get("homeTeam") or "",
                            "away": e.get("awayTeam") or "", "sport": sport,
                            "league": e.get("league") or "",
                            "time": eat.strftime("%H:%M"),
                            "kickoff_tz": eat})
            if len(evs) < PAGE:
                break
            skip += PAGE
        log(f"    · betway/{sport}: matukio {kept} ({day_iso})")
    return BookieDay(events=out, retrieved_at=clock.now_tz().isoformat(timespec="seconds"),
                     source_url=FEEDS, ok=True)


def markets_all(event_id: str, timeout: int = 25) -> tuple[list, list, dict]:
    mig, outs, prices = [], [], []
    skip = 0
    while skip < 1000:
        q = (f"/MarketGroupings/MarketGroupNamesAndMarketsForEvent?eventId={event_id}"
             f"&marketGroupId=%20&countryCode=TZ&cultureCode=en-US&skip={skip}&take=100"
             f"&isBuildABetOnly=false&searchQuery=")
        d = _get(q, timeout=timeout)
        page = d.get("marketsInGroup") or []
        mig += page
        outs += d.get("outcomes") or []
        prices += d.get("prices") or []
        if len(page) < 100:
            break
        skip += 100
    return mig, outs, {p["outcomeId"]: p for p in prices}


def snapshot_event(event_id: str, timeout: int = 25) -> list[Offer]:
    """Masoko YOTE ya tukio moja — hii ndiyo msingi wa ugunduzi na uthibitishaji."""
    mig, outs, pmap = markets_all(event_id, timeout=timeout)
    ts = clock.now_tz().isoformat(timespec="seconds")
    url = f"{FEEDS}/MarketGroupings/MarketGroupNamesAndMarketsForEvent?eventId={event_id}"
    rows: list[Offer] = []
    for m in mig:
        mid = m.get("marketId")
        for o in outs:
            if o.get("marketId") != mid:
                continue
            pr = pmap.get(o.get("outcomeId"))
            rows.append(Offer(
                bookmaker=NAME,
                market=str(m.get("marketTypeCName") or m.get("name") or ""),
                market_name=str(m.get("name") or "").strip("[]"),
                outcome=str(o.get("name") or ""),
                odds=(pr or {}).get("priceDecimal"),
                line=o.get("handicap"),
                suspended=(pr is None) or bool(m.get("isSuspended")),
                event_id=str(event_id), retrieved_at=ts, source_url=url,
            ))
    return rows


def find_price(offers: list[Offer], predicate) -> Offer | None:
    for o in offers:
        try:
            if predicate(o):
                return o
        except Exception:  # noqa: BLE001
            continue
    return None
