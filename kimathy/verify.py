"""verify.py — uhakiki wa mwisho kabla ya export (Sehemu 13).

Mara moja kabla ya kuandika Excel:
  * tukio bado ni la leo (saa ya Tanzania),
  * halijaanza / kwisha / kuahirishwa / kufutwa,
  * muda wa kuanza bado ≥ dakika N mbele,
  * soko na chaguo bado vinatolewa,
  * odds bado ni halali na hazijabadilika kiasi cha kuharibu safu ya accumulator,
  * hakuna mechi iliyorudiwa.

Chaguo linaloshindwa linaondolewa, kisha kiboreshaji kinaendeshwa tena.
"""
from __future__ import annotations

from . import clock


def verify_leg(leg: dict, provider, cfg, reference=None,
               day=None) -> tuple[bool, str]:
    min_min = int(cfg.get("min_minutes_before_kickoff", 60))
    ok, why = clock.eligibility(leg.get("kickoff_tz"), "Scheduled",
                               reference=reference, min_minutes=min_min, day=day)
    if not ok:
        return False, f"muda:{why}"

    offers = []
    if provider is not None:
        rec = {"home": leg.get("home"), "away": leg.get("away"),
               "sport": leg.get("sport"), "kickoff_tz": leg.get("kickoff_tz")}
        offers, _used = provider.discover_markets(rec)
    if provider is None or not offers:
        # Bila bookmaker haiwezekani kuthibitisha bei — hatuwezi kudai uthibitisho.
        return False, "bei_haikuweza_kuthibitishwa_tena"

    hit = provider.select_offer(offers, leg.get("market_name", ""),
                                leg.get("selection_bookmaker") or leg.get("selection", ""),
                                leg.get("line"), False, rec)
    if hit is None:
        return False, "soko_hakito lewi_tena"
    if not hit.usable:
        return False, "bei_imesimamishwa"
    new_odds = float(hit.odds)
    if abs(new_odds - float(leg["odds"])) > 0.001:
        leg["odds"] = new_odds
        leg["odds_retrieved_at"] = hit.retrieved_at
        leg.setdefault("reasons", []).append(f"bei imesasishwa → {new_odds}")
    return True, "imethibitishwa"


def reverify(accumulator, provider, cfg, log=print, reference=None, day=None):
    """Hakiki upya accumulator. Rudia (miguu iliyobaki, orodha ya zilizondolewa)."""
    kept, dropped = [], []
    for leg in (accumulator.legs if accumulator else []):
        ok, why = verify_leg(leg, provider, cfg, reference=reference, day=day)
        if ok:
            kept.append(leg)
        else:
            dropped.append((leg, why))
            log(f"  ✗ uhakiki: {leg.get('match')} — {leg.get('market_name')} "
                f"{leg.get('selection')} → IMEONDOLEWA ({why})")
    return kept, dropped


def check_duplicates(legs: list[dict]) -> list[str]:
    seen, dups = set(), []
    for l in legs:
        k = (l.get("home", ""), l.get("away", ""))
        if k in seen:
            dups.append(l.get("match", "?"))
        seen.add(k)
    return dups
