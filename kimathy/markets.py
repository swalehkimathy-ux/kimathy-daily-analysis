"""markets.py — katalogi ya masoko NA mahitaji ya data kwa kila soko (Sehemu 7).

Kanuni kuu: **soko bila data mahususi halichambuliwi.** Kila soko linaorodhesha
`requires` — orodha ya vitu vinavyopaswa kuwepo kwenye rekodi. Vikikosekana, soko
linaondolewa na sababu ya wazi inaandikwa. Hakuna kujaza mapengo kwa makadirio.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MarketDef:
    key: str
    sport: str
    name: str                 # jina la kimataifa (linaonyeshwa kwenye Excel)
    requires: tuple = ()      # vitu lazima viwe kwenye rekodi
    selections: tuple = ()    # chaguo za kawaida (kama hazitegemei mstari)
    lines: tuple = ()         # mistari inayowezekana
    high_variance: bool = False
    note: str = ""


# ---------------------------------------------------------------------------
# MPIRA WA MIGUU
# ---------------------------------------------------------------------------
FOOTBALL = [
    MarketDef("1x2", "football", "Match Winner (1X2)",
              requires=("probs_1x2",), selections=("1", "X", "2")),
    MarketDef("double_chance", "football", "Double Chance",
              requires=("probs_1x2",), selections=("1X", "X2", "12")),
    MarketDef("draw_no_bet", "football", "Draw No Bet",
              requires=("probs_1x2",), selections=("1", "2")),
    MarketDef("total_goals", "football", "Total Goals",
              requires=("goal_expectation",), lines=(0.5, 1.5, 2.5, 3.5, 4.5)),
    MarketDef("btts", "football", "Both Teams to Score",
              requires=("goal_expectation",), selections=("Yes", "No")),
    MarketDef("team_goals", "football", "Team Goals",
              requires=("goal_expectation", "goal_split"), lines=(0.5, 1.5)),
    MarketDef("asian_handicap", "football", "Asian Handicap",
              requires=("goal_expectation",),
              lines=(-2.5, -1.5, -0.5, 0.5, 1.5, 2.5),
              note="Mistari halisi hutoka kwa bookmaker; model inakadiria tu inayopatikana."),
    MarketDef("european_handicap", "football", "European Handicap (+2)",
              requires=("goal_expectation",), selections=("+2 Home", "Draw +2", "+2 Away")),
    MarketDef("first_to_score", "football", "First Team to Score",
              requires=("goal_expectation", "goal_split"),
              selections=("Home", "Away", "None")),
    MarketDef("correct_score", "football", "Correct Score",
              requires=("goal_expectation",), high_variance=True,
              note="Uwezekano mdogo sana; inaruhusiwa tu kama bookmaker inatoa na odds zinastahili."),
    MarketDef("winning_margin", "football", "Winning Margin",
              requires=("goal_expectation",), high_variance=True),
    MarketDef("halftime_result", "football", "Half-Time Result",
              requires=("halftime_data",),
              note="HAIWEZEKANI: Forebet haichapishi data ya nusu ya kwanza."),
    MarketDef("halftime_goals", "football", "Half-Time Goals",
              requires=("halftime_data",),
              note="HAIWEZEKANI: hakuna data ya magoli ya nusu ya kwanza."),
    MarketDef("corners", "football", "Corners",
              requires=("corners_stats",),
              note="HAIWEZEKANI: hakuna chanzo cha takwimu za kona katika vyanzo vilivyosanidiwa."),
    MarketDef("cards", "football", "Cards",
              requires=("cards_stats", "referee_stats",),
              note="HAIWEZEKANI: hakuna takwimu za kadi wala mwelekeo wa mwamuzi."),
    MarketDef("fouls", "football", "Fouls",
              requires=("fouls_stats",),
              note="HAIWEZEKANI: hakuna takwimu za madhambi."),
    MarketDef("headed_goals", "football", "Headed Goals",
              requires=("headed_goals_stats",),
              note="HAIWEZEKANI: wastani wa jumla wa magoli hautosha kwa soko hili."),
    MarketDef("player_shots", "football", "Player Shots",
              requires=("player_availability", "player_shot_stats"),
              note="HAIWEZEKANI: hakuna data ya mchezaji."),
    MarketDef("player_goals", "football", "Player Goals / Assists",
              requires=("player_availability", "player_goal_stats"),
              note="HAIWEZEKANI: hakuna data ya mchezaji."),
]

# ---------------------------------------------------------------------------
# MPIRA WA KIKAPU
# ---------------------------------------------------------------------------
BASKETBALL = [
    MarketDef("winner", "basketball", "Match Winner (incl. OT)",
              requires=("probs_2way",)),
    MarketDef("handicap", "basketball", "Point Spread",
              requires=("probs_2way", "avg_points"), lines=(5.5, 9.5, 12.5)),
    MarketDef("total_points", "basketball", "Total Points",
              requires=("avg_points",), lines=(-10, -5, 0, 5)),
    MarketDef("team_points", "basketball", "Team Points",
              requires=("avg_points", "team_points_split"),
              note="HAIWEZEKANI: hakuna mgawanyo wa pointi kwa timu."),
    MarketDef("quarter_winner", "basketball", "Quarter Winner",
              requires=("quarter_data",),
              note="HAIWEZEKANI: hakuna data ya robo."),
    MarketDef("quarter_total", "basketball", "Quarter/Half Totals",
              requires=("quarter_data",),
              note="HAIWEZEKANI: hakuna data ya robo/nusu."),
    MarketDef("player_points", "basketball", "Player Points/Rebounds/Assists",
              requires=("player_availability", "player_rate_stats"),
              note="HAIWEZEKANI: hakuna data ya mchezaji wala upatikanaji wake."),
]

# ---------------------------------------------------------------------------
# TENISI
# ---------------------------------------------------------------------------
TENNIS = [
    MarketDef("winner", "tennis", "Match Winner",
              requires=("probs_2way",)),
    MarketDef("games_handicap", "tennis", "Games Handicap",
              requires=("probs_2way", "avg_games", "best_of"), lines=(3.5,)),
    MarketDef("total_games", "tennis", "Total Games",
              requires=("avg_games", "best_of"), lines=(-3, 0, 3)),
    MarketDef("set_winner", "tennis", "Set Winner",
              requires=("set_level_data",),
              note="HAIWEZEKANI: hakuna data ya kiwango cha seti kwa uso wa uwanja."),
    MarketDef("set_score", "tennis", "Set Score",
              requires=("set_level_data",),
              note="HAIWEZEKANI: hakuna data ya kiwango cha seti."),
    MarketDef("player_wins_set", "tennis", "Player to Win at Least One Set",
              requires=("set_level_data",),
              note="HAIWEZEKANI: hakuna data ya kiwango cha seti."),
]

BY_SPORT = {"football": FOOTBALL, "basketball": BASKETBALL, "tennis": TENNIS}
ALL_MARKETS = {m.key: m for m in (FOOTBALL + BASKETBALL + TENNIS)}


def markets_for(sport: str) -> list[MarketDef]:
    return list(BY_SPORT.get(sport, []))


def eligibility(m: MarketDef, evidence: dict) -> tuple[bool, str]:
    """Je, tuna data mahususi ya kutosha kuchambua soko hili?

    `evidence` = set ya vitu vilivyopatikana, mf. {"probs_1x2", "goal_expectation"}.
    """
    missing = [r for r in m.requires if r not in evidence]
    if missing:
        return False, "data_inakosekana:" + ",".join(missing)
    return True, "data_yatosha"


def discoverable(m: MarketDef) -> bool:
    """Je, soko hili lina uwezekano wa kuwepo kwenye bookmaker (lina model)?"""
    blockers = {"halftime_data", "corners_stats", "cards_stats", "referee_stats",
                "fouls_stats", "headed_goals_stats", "player_availability",
                "player_shot_stats", "player_goal_stats", "player_rate_stats",
                "quarter_data", "set_level_data", "team_points_split"}
    return not (set(m.requires) & blockers)


def full_name(market_name: str, selection: str, line=None) -> str:
    if line is None:
        return f"{market_name} — {selection}"
    return f"{market_name} {line:g} — {selection}"
