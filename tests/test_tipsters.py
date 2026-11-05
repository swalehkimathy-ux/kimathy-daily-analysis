"""Majaribio: vyanzo vya maoni (tipsters) — hakuna kubuni utabiri (Sehemu 8)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kimathy import tipsters
from tests._fixtures import rec

URL = "https://example.test/predictions"


def main():
    fixtures = [rec("Team Alpha", "Team Beta", 57, 30, 13, avg=3.0),
                rec("Team Gamma", "Team Delta", 36, 33, 31, avg=2.1)]

    # 1. maoni yanayotaja mechi ya leo + soko linalotambulika → yanarekodiwa
    html = """
    <html><body>
    <p>Today's tip: Team Alpha vs Team Beta should see both teams to score.
       The home side has scored in eight straight games.</p>
    <p>Elsewhere, Team Gamma vs Team Delta looks like a low-scoring affair,
       so we favour under 2.5 goals in that one.</p>
    <p>Unrelated paragraph about a completely different fixture entirely here now.</p>
    </body></html>
    """
    items = tipsters.extract_opinions(html, fixtures, source="test", url=URL,
                                      retrieved_at="2026-11-05T12:00:00+03:00")
    assert len(items) == 2, items
    markets_found = sorted(i["market"] for i in items)
    assert markets_found == ["BTTS", "Under 2.5"], markets_found

    # 2. kila rekodi ni 'opinion_only' na HAINA uwezekano (hatubuni takwimu)
    for i in items:
        assert i["trust"] == "opinion_only", i
        assert i["probability"] is None, i
        assert i["source_url"] == URL and i["retrieved_at"], i
        assert i["raw_text"], "ushahidi ghafi ni lazima"

    # 3. maandishi yasiyo na mechi za leo → hakuna kinachobuniwa
    empty = tipsters.extract_opinions(
        "<html><body><p>" + ("lorem ipsum dolor sit amet " * 30) +
        "Chelsea to win against Arsenal with over 2.5 goals expected tonight.</p></body></html>",
        fixtures, source="test", url=URL, retrieved_at="2026-11-05T12:00:00+03:00")
    assert empty == [], empty

    # 4. ukurasa uliozuiliwa/mfupi → hakuna maoni (si makosa ya kimya kimya)
    short = tipsters.extract_opinions("<html><body>Just a moment...</body></html>", fixtures,
                                      source="test", url=URL, retrieved_at="x")
    assert short == []

    # 5. ripoti ya uhuru: makubaliano ya wengi si ushahidi
    note = tipsters.note_independence([{"ok": True}, {"ok": True}, {"ok": False}])
    assert "HAYAHESABIWI" in note, note

    # 6. kufanya kundi kwa tukio
    grouped = tipsters.group_by_event(items)
    assert len(grouped) == 2

    print("✓ tipsters: ALL GREEN (6 makundi — maoni tu, hakuna uwezekano unaobuniwa)")


if __name__ == "__main__":
    main()
