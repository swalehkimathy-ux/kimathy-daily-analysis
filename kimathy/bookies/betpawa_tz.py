"""bookies/betpawa_tz.py — betPawa Tanzania (chanzo cha UGUNDUZI WA MASOKO).

Sababu ya kuchaguliwa: endpoint `/events/{id}` inarudisha masoko YOTE ya tukio
(sio 1X2 tu), ndiyo maana ndiyo chanzo cha "gundua masoko kwa upana" (Sehemu 7).

Kichwa cha lazima: `X-Pawa-Brand: betpawa-tanzania`.
Bila kichwa hiki API inarudisha 400 `BRAND_HEADER_IS_MISSING` — nimekithibitisha.
"""
from __future__ import annotations

import datetime as _dt
import json
import urllib.parse

from .. import clock
from .base import BookieDay, Offer, json_get

NAME = "betpawa"
BASE = "https://www.betpawa.co.tz/api/sportsbook/v4"
HDRS = {
    "X-Pawa-Brand": "betpawa-tanzania",
    "X-Pawa-Language": "en",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KimathyEngine/1.0",
    "Accept": "application/json",
}
CATEGORY = {"football": "2", "basketball": "3", "tennis": "452"}
TAKE = 100


def _get(path: str, timeout: int = 25, tries: int = 2) -> dict:
    return json_get(BASE + path, HDRS, timeout=timeout, tries=tries)


def _walk_events(obj, acc: list) -> None:
    if isinstance(obj, dict):
        if "participants" in obj:
            acc.append(obj)
        for v in obj.values():
            _walk_events(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _walk_events(v, acc)


def day_index(day_iso: str, sports: list[str], log=print, timeout: int = 25) -> BookieDay:
    out: list[dict] = []
    for sport, cat in CATEGORY.items():
        if sport not in sports:
            continue
        q = {"queries": [{"query": {"eventType": "UPCOMING", "categories": [cat]},
                          "sort": {"popularity": "DESC"}, "take": TAKE}]}
        path = "/events/lists/by-queries?q=" + urllib.parse.quote(json.dumps(q))
        data = _get(path, timeout=timeout)
        evs: list = []
        _walk_events(data, evs)
        n_day = 0
        for e in evs:
            st = e.get("startTime")
            if not st:
                continue
            try:
                eat = _dt.datetime.fromisoformat(str(st).replace("Z", "+00:00")).astimezone(clock.TZ)
            except ValueError:
                continue
            if eat.date().isoformat() != day_iso:
                continue
            n_day += 1
            parts = e.get("participants") or []
            home = parts[0].get("name") if parts else ""
            away = parts[1].get("name") if len(parts) > 1 else ""
            out.append({"id": e.get("id"), "name": e.get("name") or "",
                        "home": home, "away": away, "sport": sport,
                        "league": (e.get("competition") or {}).get("name") or "",
                        "time": eat.strftime("%H:%M"), "kickoff_tz": eat})
        log(f"    · betPawa/{sport}: matukio {n_day} ({day_iso})")
    return BookieDay(events=out, retrieved_at=clock.now_tz().isoformat(timespec="seconds"),
                     source_url=BASE, ok=True)


def markets(event_id, timeout: int = 25) -> list[dict]:
    data = _get(f"/events/{event_id}", timeout=timeout)
    ev = data.get("event") or data
    return ev.get("markets") or []


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def snapshot_event(event_id, timeout: int = 25) -> list[Offer]:
    """Masoko YOTE ya tukio — jina la soko, mstari, chaguo, odds, hali ya kusimamishwa.

    Muundo halisi wa API (umethibitishwa kwa data hai, 2026-11-05):
        markets[i]["marketType"] = {"id","name","displayName", ...}
        markets[i]["row"][j]["specifier"] = {"total": "2.5"} | {"hcp": "-1.5"} | {"number": "1"}
        markets[i]["row"][j]["prices"][k] = {"name","odds","suspended","probability":{"win":..}}

    KUMBUKA: toleo la zamani la code lilisoma `m["betTypeId"]` na `m["name"]` — njia hizo
    HAZIPO tena, ndiyo maana majina ya masoko yalikuwa matupu. Imerekebishwa hapa.
    """
    ts = clock.now_tz().isoformat(timespec="seconds")
    url = f"{BASE}/events/{event_id}"
    rows: list[Offer] = []
    for m in markets(event_id, timeout=timeout):
        mt = m.get("marketType") or {}
        mk_id = str(mt.get("id") or "")
        mk_name = str(mt.get("name") or "")
        mk_display = str(mt.get("displayName") or "")
        for row in (m.get("row") or []):
            spec = row.get("specifier") or {}
            raw_line = spec.get("total") if spec.get("total") is not None else spec.get("hcp")
            line = _to_float(raw_line)
            for p in (row.get("prices") or []):
                prob = (p.get("probability") or {}).get("win")
                rows.append(Offer(
                    bookmaker=NAME,
                    market=mk_id,
                    market_name=mk_name,
                    outcome=str(p.get("name") or ""),
                    odds=_to_float(p.get("odds")),
                    line=line,
                    suspended=bool(p.get("suspended")),
                    event_id=str(event_id), retrieved_at=ts, source_url=url,
                    display_name=mk_display,
                    bookmaker_prob=_to_float(prob),
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
