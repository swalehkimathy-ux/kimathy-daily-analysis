"""bookies/provider.py — ugunduzi wa masoko, uthibitishaji wa bei, na usawazishaji.

Kazi:
  1. Kujenga orodha ya matukio ya siku kutoka bookmaker walio washwa.
  2. Kulinganisha mechi ya Forebet na tukio la bookmaker (bila kukisia).
  3. Kunakili masoko YOTE ya tukio (ugunduzi mpana — Sehemu 7).
  4. Kuthibitisha soko+chaguo mahususi na kurudisha bei halisi.
  5. Kuzuia bookmaker aliyekufa kuharibu uendeshaji (circuit breaker + budget).

Kila kitu kinarudishwa na asili ya data: bookmaker, URL, muda wa kukusanya.
"""
from __future__ import annotations

from .. import clock, normalize
from . import afropari_tz, betpawa_tz, betway_tz
from .base import BookieError, Breaker, Offer, combine_probs, devig, disagree, overround

ADAPTERS = {
    "betway_tz": betway_tz,
    "betpawa_tz": betpawa_tz,
    "afropari": afropari_tz,
}


class Provider:
    def __init__(self, cfg, log=print):
        self.cfg = cfg
        self.log = log
        self.day = clock.today_tz().isoformat()
        self.sports = list(cfg.get("sports", ["football", "basketball", "tennis"]))
        bk = cfg.section("bookmakers")
        self.names = [n for n, m in bk.items() if m.get("enabled")]
        self.breakers = {n: Breaker(fail_limit=5, budget_s=480.0) for n in self.names}
        self.index: dict[str, list[dict]] = {}
        self.down: dict[str, str] = {}
        self.market_cache: dict[tuple[str, str], list[Offer]] = {}
        self.discovery_names = [n for n in self.names
                               if bk.get(n, {}).get("market_discovery")
                               and getattr(ADAPTERS.get(n), "IMPLEMENTED", True) is not False]
        self.stats = {"index_events": {}, "snapshots": 0, "verified": 0,
                      "not_found": 0, "unmatched": 0}

    # ------------------------------------------------------------ orodha ya siku
    def build_index(self) -> None:
        for name in self.names:
            mod = ADAPTERS.get(name)
            if mod is None:
                self.down[name] = "adapter haipo"
                continue
            if getattr(mod, "IMPLEMENTED", True) is False:
                self.down[name] = "haijatekelezwa (adapter ni stub)"
                self.log(f"    · {name}: HAIJATEKELEZWA — imeachwa")
                continue
            br = self.breakers[name]
            if not br.allow():
                self.down[name] = "budget/kikomo cha makosa kimefikiwa"
                continue
            try:
                res = mod.day_index(self.day, self.sports, log=self.log)
                self.index[name] = res.events
                self.stats["index_events"][name] = len(res.events)
                br.ok()
            except BookieError as e:
                self.down[name] = str(e)[:160]
                br.fail()
                self.log(f"    ✗ {name}: haifikiki ({str(e)[:90]}) — haitajaribiwa tena kwa run hii")
            except NotImplementedError as e:
                self.down[name] = str(e)[:160]

    def available(self) -> list[str]:
        return [n for n in self.names if n in self.index and self.index[n]]

    # ------------------------------------------------------------- ulinganishaji
    def match_event(self, name: str, rec: dict) -> tuple[dict | None, bool, float, str]:
        events = self.index.get(name) or []
        if not events:
            return None, False, 0.0, "bookmaker_haifikiki"
        ko = clock.to_tz(rec.get("kickoff_tz"))
        our_time = ko.strftime("%H:%M") if ko else ""
        same_sport = [e for e in events if e.get("sport") == rec.get("sport")]
        return normalize.find_event(same_sport, rec.get("home", ""), rec.get("away", ""), our_time)

    # ------------------------------------------------------------------ masoko
    def snapshot(self, name: str, event_id, flipped: bool = False) -> list[Offer]:
        key = (name, str(event_id))
        if key in self.market_cache:
            return self.market_cache[key]
        mod = ADAPTERS.get(name)
        br = self.breakers[name]
        if mod is None or not br.allow():
            return []
        try:
            offers = mod.snapshot_event(event_id)
            self.market_cache[key] = offers
            self.stats["snapshots"] += 1
            br.ok()
            return offers
        except BookieError as e:
            br.fail()
            self.log(f"    ⚠ {name}: masoko ya tukio {event_id} yameshindwa ({str(e)[:70]})")
            self.market_cache[key] = []
            return []

    def discover_markets(self, rec: dict) -> tuple[list[Offer], str]:
        """Rudisha masoko YOTE yanayopatikana kwa mechi hii (kwa upana, si orodha fupi)."""
        out: list[Offer] = []
        used = []
        for name in self.discovery_names or self.available():
            ev, flipped, score, why = self.match_event(name, rec)
            if not ev:
                continue
            out.extend(self.snapshot(name, ev["id"], flipped))
            used.append(name)
        return out, ",".join(used) if used else ""

    # --------------------------------------------------------------- uthibitishaji
    def verify(self, rec: dict, market_name: str, selection: str,
               line=None) -> dict:
        """Thibitisha kuwa soko+chaguo lipo kweli na rudisha bei halisi.

        Rudisha dict: {ok, odds, bookmaker, market, offer, reason, candidates}
        """
        tried = []
        for name in self.available():
            ev, flipped, score, why = self.match_event(name, rec)
            if not ev:
                self.stats["unmatched"] += 1
                tried.append(f"{name}: {why}")
                continue
            offers = self.snapshot(name, ev["id"], flipped)
            if not offers:
                tried.append(f"{name}: masoko_hayakupatikana")
                continue
            hit = self._select_offer(offers, market_name, selection, line, flipped, rec)
            if hit is None:
                self.stats["not_found"] += 1
                tried.append(f"{name}: soko_halitolewi")
                continue
            if not hit.usable:
                tried.append(f"{name}: bei_imesimamishwa_au_haijulikani")
                continue
            self.stats["verified"] += 1
            return {"ok": True, "odds": float(hit.odds), "bookmaker": name,
                    "market": hit.market_name or hit.market, "selection": hit.outcome,
                    "line": hit.line, "offer": hit, "source_url": hit.source_url,
                    "retrieved_at": hit.retrieved_at, "all_offers": offers,
                    "flipped": flipped}
        return {"ok": False, "odds": None, "bookmaker": None, "reason": " | ".join(tried)
                or "hakuna bookmaker aliyepatikana"}

    def select_offer(self, offers: list[Offer], market_name: str, selection: str,
                     line=None, flipped: bool = False, rec: dict | None = None) -> Offer | None:
        """Umuma: tafuta Offer inayolingana ndani ya orodha ya masoko iliyokusanywa."""
        return self._select_offer(offers, market_name, selection, line, flipped, rec or {})

    def _select_offer(self, offers: list[Offer], market_name: str, selection: str,
                      line, flipped: bool, rec: dict) -> Offer | None:
        """Tafuta Offer inayolingana. Tunalinganisha kwa maandishi ya bookmaker —
        hatubadilishi majina ya asili."""
        want_m = normalize.normalize(market_name)
        want_s = normalize.normalize(selection)
        home_n = normalize.normalize(rec.get("home", ""))
        away_n = normalize.normalize(rec.get("away", ""))
        best = None
        best_score = -1.0
        for o in offers:
            m_norm = normalize.normalize(o.market_name or o.market)
            s_norm = normalize.normalize(o.outcome)
            if not m_norm or not s_norm:
                continue
            ms = normalize.team_sim(market_name, o.market_name or o.market)
            ss = normalize.team_sim(selection, o.outcome)
            # majina ya timu yanayogeuzwa (flipped) — "Home" ↔ jina la away
            if selection in ("Home", "1", "1X", "+2 Home", "Over Home"):
                target = away_n if flipped else home_n
                if target and target in s_norm:
                    ss = 1.0
            elif selection in ("Away", "2", "X2", "+2 Away", "Over Away"):
                target = home_n if flipped else away_n
                if target and target in s_norm:
                    ss = 1.0
            if line is not None and o.line is not None:
                try:
                    if abs(float(o.line) - float(line)) > 0.01:
                        continue
                except (TypeError, ValueError):
                    continue
            score = ms * 0.4 + ss * 0.6
            if ss < 0.6 or ms < 0.45:
                continue
            if score > best_score:
                best, best_score = o, score
        return best

    # ------------------------------------------------------------------- devig
    def market_probabilities(self, offers: list[Offer], market_name: str,
                             outcomes: list[str], line=None) -> dict:
        """Devig + changanya uwezekano wa soko moja kutoka bookmaker wote.

        Rudisha {"probs": [..], "by_bookmaker": {...}, "overround": x,
                 "single_source": bool, "disagree": [bool,...], "n": k}
        """
        want_m = normalize.normalize(market_name)
        per_bookie: dict[str, list[float | None]] = {}
        ors: dict[str, float] = {}
        for name in self.available():
            rows = [o for o in offers if o.bookmaker == name and o.usable]
            if not rows:
                continue
            chosen: list[Offer | None] = []
            for sel in outcomes:
                hit = None
                for o in rows:
                    if normalize.normalize(o.market_name or o.market) != want_m:
                        continue
                    if line is not None and o.line is not None:
                        try:
                            if abs(float(o.line) - float(line)) > 0.01:
                                continue
                        except (TypeError, ValueError):
                            continue
                    if normalize.team_sim(sel, o.outcome) >= 0.85:
                        hit = o
                        break
                chosen.append(hit)
            if any(c is None for c in chosen):
                continue
            odds_list = [float(c.odds) for c in chosen]
            total = 2.0 if len(odds_list) == 3 and normalize.normalize(market_name).startswith("double") else 1.0
            per_bookie[name] = devig(odds_list, total=total)
            ors[name] = overround(odds_list)
        if not per_bookie:
            return {"probs": [], "by_bookmaker": {}, "overround": None,
                    "single_source": True, "disagree": [], "n": 0}
        entries = [(p, 1.0) for p in per_bookie.values()]
        probs = combine_probs(entries)
        lists = list(per_bookie.values())
        dis = [disagree(lists, i) for i in range(len(outcomes))] if len(lists) >= 2 else []
        ors_vals = [v for v in ors.values() if v is not None]
        return {"probs": probs, "by_bookmaker": per_bookie,
                "overround": round(sum(ors_vals) / len(ors_vals), 6) if ors_vals else None,
                "single_source": len(per_bookie) == 1,
                "disagree": dis, "n": len(per_bookie)}

    def report(self) -> dict:
        return {"bookmakers_enabled": self.names,
                "bookmakers_available": self.available(),
                "bookmakers_down": dict(self.down),
                "index_events": self.stats["index_events"],
                "snapshots": self.stats["snapshots"],
                "verified_offers": self.stats["verified"],
                "market_not_offered": self.stats["not_found"],
                "unmatched_events": self.stats["unmatched"]}
