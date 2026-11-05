"""Majaribio: usawazishaji wa majina, ulinganishaji wa matukio, marudio."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kimathy import normalize


def main():
    # 1. token za kutofautisha — makosa ya zamani (B1 ya spec)
    assert normalize.team_sim("Inter", "Inter Miami") == 0.0
    assert normalize.team_sim("Barcelona", "Barcelona SC") == 0.0
    assert normalize.team_sim("Lyon", "Lyon W") == 0.0
    assert normalize.team_sim("Arsenal", "Arsenal Tula") == 0.0

    # 2. majina sawa / aliases
    assert normalize.team_sim("Man City", "Manchester City") == 1.0
    assert normalize.team_sim("Bayern", "Bayern Munich") == 1.0
    assert normalize.team_sim("PSG", "Paris Saint Germain") == 1.0
    assert normalize.team_sim("Simba", "Simba SC") == 1.0

    # 3. yasiyolingana kabisa
    assert normalize.team_sim("Chelsea", "Liverpool") < 0.5

    # 4. ulinganishaji wa tukio — muda ndani ya ±20 dk
    events = [{"home": "Manchester City", "away": "Chelsea", "time": "20:00"},
              {"home": "Manchester City", "away": "Chelsea", "time": "12:00"}]
    ev, flipped, sc, why = normalize.find_event(events, "Man City", "Chelsea", "20:00")
    assert ev is not None and ev["time"] == "20:00", (ev, why)

    # 5. muda haujulikani → jina lazima lifanane HASWA (au alias); vinginevyo KATAA
    ev2, _, sc2, why2 = normalize.find_event(
        [{"home": "Borussia Dortmund II", "away": "Werder Bremen II", "time": ""}],
        "Borussia Dortmund", "Werder Bremen", "")
    assert ev2 is None and sc2 == 0.0, (sc2, why2)
    ev2c, _, sc2c, why2c = normalize.find_event(
        [{"home": "Borussia Dortmund", "away": "Werder Bremen", "time": ""}],
        "Borussia Dortmund", "Werder Bremen U21", "")
    assert ev2c is None, (sc2c, why2c)
    # jina linalofanana haswa linakubaliwa hata bila muda; "FC" ni stopword
    ev2b, _, sc2b, why2b = normalize.find_event(
        [{"home": "FC Borussia Dortmund", "away": "Werder Bremen", "time": ""}],
        "Borussia Dortmund", "Werder Bremen", "")
    assert ev2b is not None and sc2b >= 0.999, (sc2b, why2b)

    # 6. utata (matukio mawili yanayofanana sawa) → KATAA, usikisie
    amb = [{"home": "Arsenal", "away": "Chelsea", "time": "20:00"},
           {"home": "Arsenal", "away": "Chelsea", "time": "20:00"}]
    ev3, _, _, why3 = normalize.find_event(amb, "Arsenal", "Chelsea", "20:00")
    assert ev3 is None and "utata" in why3, why3

    # 7. hakuna kinacholingana
    ev4, _, sc4, why4 = normalize.find_event([{"home": "Ajax", "away": "PSV", "time": "18:00"}],
                                             "Arsenal", "Spurs", "18:00")
    assert ev4 is None and sc4 == 0.0

    # 8. marudio yanaondolewa
    recs = [{"home": "Simba", "away": "Yanga", "kickoff_tz": "2026-11-05T20:00"},
            {"home": "Simba SC", "away": "Young Africans", "kickoff_tz": "2026-11-05T20:00"}]
    out, removed = normalize.dedupe(recs)
    assert removed == 0, "majina tofauti ya kawaida hayapaswi kuunganishwa bila ulinganishaji"

    recs2 = [{"home": "Simba", "away": "Yanga", "kickoff_tz": "2026-11-05T20:00"},
             {"home": "Simba", "away": "Yanga", "kickoff_tz": "2026-11-05T20:00"}]
    out2, removed2 = normalize.dedupe(recs2)
    assert len(out2) == 1 and removed2 == 1

    # 9. normalize inashughulikia unicode na alama
    assert normalize.normalize("  Atlético  Madrid  ") == "atletico madrid"
    assert normalize.normalize("FC Köln") == "fc koln"

    print("✓ normalize: ALL GREEN (9 makundi — token, aliases, muda ±20dk, utata, marudio)")


if __name__ == "__main__":
    main()
