"""clock.py — Saa ya Tanzania na sheria za muda (Sehemu 4 ya master prompt).

Kila kitu kinatumia `Africa/Dar_es_Salaam`. Hakuna "saa ya seva" wala UTC pekee.
"""
from __future__ import annotations

import datetime as _dt
from zoneinfo import ZoneInfo

TZ_NAME = "Africa/Dar_es_Salaam"
TZ = ZoneInfo(TZ_NAME)

# Hali zinazomaanisha mechi HAISTAHILI (imeanza / imeisha / imeahirishwa / imefutwa)
NOT_ELIGIBLE_PREFIX = (
    "FT", "AET", "AP", "Pen.", "In Play", "Started", "Interrupted", "Abandoned",
    "Postponed", "Cancelled", "Suspended", "Awarded", "Walkover", "Retired",
    "Live", "HT", "ET", "After",
)
# Hali pekee inayokubalika kama "imepangwa na kuthibitishwa"
CONFIRMED_STATUSES = ("Scheduled", "", None)


def now_tz() -> _dt.datetime:
    """Saa ya sasa ya Tanzania (timezone-aware)."""
    return _dt.datetime.now(TZ)


def today_tz() -> _dt.date:
    """Tarehe ya kalenda ya Tanzania ya leo."""
    return now_tz().date()


def to_tz(value) -> _dt.datetime | None:
    """Badilisha muda wowote kuwa saa ya Tanzania. Naive inachukuliwa kuwa tayari ni EAT."""
    if value is None:
        return None
    if isinstance(value, _dt.date) and not isinstance(value, _dt.datetime):
        value = _dt.datetime(value.year, value.month, value.day)
    if not isinstance(value, _dt.datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=TZ)
    return value.astimezone(TZ)


def is_not_eligible_status(status: str | None) -> bool:
    """True kama hali ya mechi inaonyesha haistahili kuchambuliwa."""
    if status is None:
        return False
    s = str(status).strip()
    if not s:
        return False
    return any(s.startswith(p) for p in NOT_ELIGIBLE_PREFIX)


def minutes_until(kickoff, reference=None) -> float | None:
    """Dakika zilizobaki kabla ya kuanza. Hasara = mechi imekwishaanza."""
    ko = to_tz(kickoff)
    if ko is None:
        return None
    ref = to_tz(reference) if reference is not None else now_tz()
    return (ko - ref).total_seconds() / 60.0


def eligibility(kickoff, status, *, reference=None, min_minutes: int = 60,
                day=None) -> tuple[bool, str]:
    """Amua kama mechi inastahili. Rudia (bool, sababu).

    Sheria (Sehemu 4):
      1. leo tu (kalenda ya Tanzania),
      2. hali haijaanza/kwisha/kuahirishwa/kufutwa,
      3. angalau `min_minutes` dakika mbele,
      4. sio baada ya usiku wa manane wa siku inayofuata.
    """
    ko = to_tz(kickoff)
    if ko is None:
        return False, "muda_wa_kuanza_haujulikani"
    ref = to_tz(reference) if reference is not None else now_tz()

    target_day = day if day is not None else ref.date()
    if ko.date() != target_day:
        return False, f"sio_leo:{ko.date().isoformat()}"

    if is_not_eligible_status(status):
        return False, f"hali_haistahili:{status}"

    mins = (ko - ref).total_seconds() / 60.0
    if mins < 0:
        return False, "imekwishaanza"
    if mins < float(min_minutes):
        return False, f"chini_ya_dakika_{min_minutes}:{mins:.0f}dk"
    return True, "inastahili"


def fmt_tz(value, with_seconds: bool = False) -> str:
    t = to_tz(value)
    if t is None:
        return ""
    return t.strftime("%Y-%m-%d %H:%M" + (":%S" if with_seconds else ""))


def stamp_for_filename(reference=None) -> str:
    t = to_tz(reference) if reference is not None else now_tz()
    return t.strftime("%Y-%m-%d_%H-%M")
