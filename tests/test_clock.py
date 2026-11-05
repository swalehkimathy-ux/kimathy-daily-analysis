"""Majaribio: saa ya Tanzania + sheria za muda (Sehemu 4)."""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kimathy import clock

REF = _dt.datetime(2026, 11, 5, 15, 0, 0, tzinfo=clock.TZ)


def main():
    # 1. saa ya Tanzania ni aware na iko UTC+3
    n = clock.now_tz()
    assert n.tzinfo is not None
    assert n.utcoffset() == _dt.timedelta(hours=3), n.utcoffset()

    # 2. mechi ya 15:45 (dakika 45) → HAISTAHILI (chini ya 60)
    ko = _dt.datetime(2026, 11, 5, 15, 45, tzinfo=clock.TZ)
    ok, why = clock.eligibility(ko, "Scheduled", reference=REF, min_minutes=60)
    assert not ok and why.startswith("chini_ya_dakika_60"), why

    # 3. mechi ya 16:00 (dakika 60) → INASTAHILI (mipaka inahesabika)
    ko = _dt.datetime(2026, 11, 5, 16, 0, tzinfo=clock.TZ)
    ok, why = clock.eligibility(ko, "Scheduled", reference=REF, min_minutes=60)
    assert ok and why == "inastahili", why

    # 4. mechi ya jana → sio leo
    ko = _dt.datetime(2026, 11, 4, 18, 0, tzinfo=clock.TZ)
    ok, why = clock.eligibility(ko, "Scheduled", reference=REF, min_minutes=60)
    assert not ok and why.startswith("sio_leo"), why

    # 5. mechi ya kesho → sio leo (haipaswi kujumuishwa)
    ko = _dt.datetime(2026, 11, 6, 10, 0, tzinfo=clock.TZ)
    ok, why = clock.eligibility(ko, "Scheduled", reference=REF, min_minutes=60)
    assert not ok and why.startswith("sio_leo"), why

    # 6. mechi iliyokwishaanza
    ko = _dt.datetime(2026, 11, 5, 14, 30, tzinfo=clock.TZ)
    ok, why = clock.eligibility(ko, "Scheduled", reference=REF, min_minutes=60)
    assert not ok and why == "imekwishaanza", why

    # 7. hali mbalimbali zisizostahili
    for st in ("FT", "AET (ET 1-0)", "Pen. (4-3)", "In Play 67'", "HT",
               "Postponed", "Cancelled", "Abandoned"):
        ko = _dt.datetime(2026, 11, 5, 20, 0, tzinfo=clock.TZ)
        ok, why = clock.eligibility(ko, st, reference=REF, min_minutes=60)
        assert not ok and why.startswith("hali_haistahili"), (st, why)

    # 8. 'Scheduled' inastahili
    ko = _dt.datetime(2026, 11, 5, 20, 0, tzinfo=clock.TZ)
    ok, _ = clock.eligibility(ko, "Scheduled", reference=REF, min_minutes=60)
    assert ok

    # 9. muda usiojulikana
    ok, why = clock.eligibility(None, "Scheduled", reference=REF, min_minutes=60)
    assert not ok and why == "muda_wa_kuanza_haujulikani", why

    # 10. UTC inabadilishwa kuwa EAT kwa usahihi
    utc_ko = _dt.datetime(2026, 11, 5, 13, 0, tzinfo=_dt.timezone.utc)   # 16:00 EAT
    t = clock.to_tz(utc_ko)
    assert t.hour == 16 and t.utcoffset() == _dt.timedelta(hours=3), t

    # 11. stamp ya faili
    s = clock.stamp_for_filename(REF)
    assert s == "2026-11-05_15-00", s

    print("✓ clock: ALL GREEN (11 makundi — muda, hali, mipaka ya dakika 60, timezone)")


if __name__ == "__main__":
    main()
