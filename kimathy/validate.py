"""validate.py — uthibitishaji wa rekodi (Sehemu 9).

Rekodi inayoshindwa HAIREKEBISHWI kimya kimya: inaondolewa na kuhesabiwa kwa sababu.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import clock

HTML_REMNANTS = ("<", ">", "&nbsp;", "&amp;")


def _bad_team_name(n) -> bool:
    if not n or not str(n).strip():
        return True
    s = str(n).strip()
    if not (2 <= len(s) <= 60):
        return True
    if any(m in s for m in HTML_REMNANTS):
        return True
    if not re.search(r"[A-Za-z0-9]", s):
        return True
    return False


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def validate_record(rec: dict, sport: str = "football") -> tuple[bool, list[str]]:
    """Rudia (ok, orodha_ya_matatizo)."""
    probs: list[str] = []
    home, away = rec.get("home"), rec.get("away")
    if _bad_team_name(home):
        probs.append("jina_la_timu_ya_nyumbani")
    if _bad_team_name(away):
        probs.append("jina_la_timu_ya_ugenini")
    if home and away and str(home).strip().lower() == str(away).strip().lower():
        probs.append("timu_zinazofanana")

    if not rec.get("league"):
        probs.append("ligi_haipo")

    ko = clock.to_tz(rec.get("kickoff_tz"))
    if ko is None:
        probs.append("muda_wa_kuanza_haujulikani")

    st = rec.get("status")
    if clock.is_not_eligible_status(st):
        probs.append(f"not_pre_match:{st}")

    # uwezekano wa Forebet
    p = rec.get("probs") or {}
    vals = [_f(p.get(k)) for k in ("1", "X", "2")] if sport == "football" else \
           [_f(p.get(k)) for k in ("1", "2")]
    if sport == "football":
        if any(v is None for v in vals):
            probs.append("uwezekano_haujakamilika")
        else:
            if any(not (0 <= v <= 100) for v in vals):
                probs.append("uwezekano_nje_ya_0_100")
            elif abs(sum(vals) - 100) > 3:
                probs.append(f"uwezekano_haujumlishi_100:{sum(vals):.0f}")
    else:
        if any(v is None for v in vals):
            probs.append("uwezekano_haujakamilika")
        elif any(not (0 <= v <= 100) for v in vals):
            probs.append("uwezekano_nje_ya_0_100")

    # odds za rejea (za Forebet) — zikipo lazima ziwe halali
    od = rec.get("odds_1x2")
    if od:
        for o in od:
            ov = _f(o)
            if ov is None or ov < 1.01 or ov > 300:
                probs.append("odds_zisizo_halali")
                break

    # matokeo yaliyotabiriwa
    ps = rec.get("predicted_score")
    if ps and len(ps) >= 2:
        a, b = _f(ps[0]), _f(ps[1])
        if a is None or b is None or not (0 <= a <= 15 and 0 <= b <= 15):
            probs.append("matokeo_yaliyotabiriwa_yasiyo_halali")

    # wastani
    avg = _f(rec.get("avg"))
    if avg is not None:
        if sport == "football" and not (0.2 <= avg <= 8.0):
            probs.append(f"wastani_wa_magoli_usio_halali:{avg}")
        elif sport == "basketball" and not (100 <= avg <= 320):
            probs.append(f"wastani_wa_pointi_usio_halali:{avg}")
        elif sport == "tennis" and not (10 <= avg <= 60):
            probs.append(f"wastani_wa_games_usio_halali:{avg}")

    if not rec.get("source_url"):
        probs.append("chanzo_cha_url_hakipo")

    return (len(probs) == 0), probs


@dataclass
class ValidationStats:
    total: int = 0
    valid: int = 0
    dropped: dict = field(default_factory=dict)

    def add(self, ok: bool, problems: list[str]) -> None:
        self.total += 1
        if ok:
            self.valid += 1
            return
        for p in problems:
            key = p.split(":", 1)[0]
            self.dropped[key] = self.dropped.get(key, 0) + 1

    @property
    def dropped_count(self) -> int:
        return self.total - self.valid

    def line(self) -> str:
        rate = (self.valid / self.total * 100) if self.total else 0.0
        top = ", ".join(f"{k}={v}" for k, v in sorted(self.dropped.items(), key=lambda x: -x[1])[:5])
        return (f"rekodi {self.total} · halali {self.valid} ({rate:.1f}%) · "
                f"zilizoondolewa {self.dropped_count}" + (f" · [{top}]" if top else ""))
