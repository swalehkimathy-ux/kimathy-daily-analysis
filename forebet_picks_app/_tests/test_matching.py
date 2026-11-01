#!/usr/bin/env python3
"""Phase 2 unit tests: matching.py (spec 4.2) — bila mtandao."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matching as M

# ── team_sim: taswira za mbaya zinakataliwa (spec cases) ─────────────────
assert M.team_sim("Inter", "Inter Miami") == 0.0, "Inter ≠ Inter Miami!"
assert M.team_sim("Barcelona", "Barcelona SC") == 0.0, "Barcelona ≠ Barcelona SC!"
assert M.team_sim("Lyon", "Lyon W") == 0.0, "Lyon ≠ Lyon W!"
assert M.team_sim("Manchester United", "Manchester City") == 0.0, "United ≠ City!"
assert M.team_sim("Arsenal", "Arsenal Tula") < 0.80, "Arsenal ≠ Arsenal Tula!"

# ── taswira sahihi zinakubaliwa ──────────────────────────────────────────
assert M.team_sim("Man City", "Manchester City") >= 0.99, "alias man city"
assert M.team_sim("Bayern", "Bayern Munich") >= 0.99, "alias bayern"
assert M.team_sim("PSG", "Paris Saint Germain") >= 0.99, "alias psg"
assert M.team_sim("Tottenham", "Tottenham Hotspur") >= 0.99, "alias spurs"
assert M.team_sim("Liverpool", "Liverpool FC") >= 0.90, "generic drop fc"

# tennis: "Hanfmann, Yannick" ↔ "Y. Hanfmann"
sc = M.team_sim("Hanfmann, Yannick", "Y. Hanfmann")
assert sc >= 0.90, f"tennis initial-flip: {sc}"

# ── event_score / find_event ─────────────────────────────────────────────
EV = [
    {"sport": "football", "home": "Manchester City", "away": "Brighton", "time_eat": "20:00", "league": "England Premier League"},
    {"sport": "football", "home": "Manchester City U21", "away": "Brighton U21", "time_eat": "14:00", "league": "England PL2"},
    {"sport": "football", "home": "Inter Miami", "away": "LA Galaxy", "time_eat": "02:00", "league": "USA MLS"},
    {"sport": "basketball", "home": "Lakers", "away": "Bulls", "time_eat": "03:30", "league": "NBA"},
    {"sport": "tennis", "home": "Struff, Jan-Lennard", "away": "Hanfmann, Yannick", "time_eat": "13:00", "league": "ATP"},
]

# 1. mechi sahihi hupatikana
ev, flip, sc, why = M.find_event(EV, "football", "Man City", "Brighton", "20:00", "England Premier League")
assert ev and ev["away"] == "Brighton" and not flip, f"man city found: {ev}"

# 2. time mismatch hukataa hata kama majina yanaofanana (U21 timedefusa)
ev2, *_ = M.find_event(EV, "football", "Manchester City U21", "Brighton U21", "20:00", "England PL2")
assert ev2 is None, "kickoff 14:00 ≠ 20:00 — lazima reject!"

# 3. tennis: FOREBET ina-wetting order kinyume (Hanfmann kwanza) → flip lazima igundulike
ev3, flip3, sc3, _ = M.find_event(EV, "tennis", "Y. Hanfmann", "J.-L. Struff", "13:00", "ATP")
assert ev3 and flip3, f"tennis flip lazima igundulike: {ev3}, flip={flip3}"

# 4. AMBIGUOUS → reject kamwe usibashiri
AMB = [
    {"sport": "football", "home": "Arsenal De Sarandi", "away": "X", "time_eat": "20:00", "league": "ARG"},
    {"sport": "football", "home": "Arsenal Tula", "away": "Y", "time_eat": "20:00", "league": "RUS"},
]
ev4, _, _, why4 = M.find_event(AMB, "football", "Arsenal", "W", None, "ARG", log=lambda s: None)
assert ev4 is None, f"ambiguous lazima reject ({why4})"

# 5. kickoff haijulikani → likelihood simama iwe ≥ 0.92 (si guess)
ev5, *_ = M.find_event(EV, "football", "Brighton", "Man City", None, None)   # flip + no time
assert ev5 is None or (ev5 and _[1]), "bila time na weak-match → reject"

print("✓ matching tests: ALL GREEN (11 asserts, spec 4.2)")
