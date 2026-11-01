# K96 SMART ENGINE — RULES (Football · Basketball · Tennis)

Companion to `K96_IMPLEMENTATION_SPEC.md`. That file says **what to build**; this file says **how the engine must think**, with rule IDs, formulas and worked examples.
All examples below come from `rules_demo.py` (run it: `python rules_demo.py`). Bookmaker odds in the demo are **synthetic** (generated with a 6% margin), so use the demo to learn the logic, not to judge profit.

**Muhtasari (Kiswahili):** Engine inafuata mpangilio mmoja kwa michezo yote: (1) zuia mechi mbovu, (2) hesabu probability ya kila soko, (3) changanya na maoni ya bookmaker, (4) chuja kwa odds/probability, (5) chagua tip moja yenye uwezekano mkubwa kwa kila mechi, (6) jenga slip yenye risk ndogo. Michezo inatofautiana kwenye hatua ya (2) na (1) tu.

---

## 0. THE PIPELINE (same for all sports)

```
record (validated) ─► BLOCK? ─► model probabilities per market ─► devig bookmaker odds
   ─► p_final = W*p_model + (1-W)*p_market ─► flags (small penalty) ─► filters
   ─► best tip per match (max probability) ─► slip builder
```

### G-rules (global)
| ID | Rule | Detail |
|---|---|---|
| G1 | **Probability, not points.** Never add "+6 form, +4 H2H" to a score. Form/H2H/home advantage are already inside Forebet's probability. | Old engine: Liverpool 57% → 98%. New engine: Liverpool 1X stays **87%** (= p1+px). |
| G2 | **Devig** bookmaker odds before using them: `p_i = (1/o_i) / Σ(1/o_j)` over a full market (for Double Chance the three outcomes sum to 2, so normalise to 2). | Demo F1 uses `devig()`. |
| G3 | **Blend:** `p_final = W_MODEL·p_model + (1−W_MODEL)·p_market`, default `W_MODEL = 0.5`. Then `p_cal = calibrate(p_final) − flag_penalty`. Calibration = identity until ≥300 settled picks exist. | |
| G4 | **Flags** only subtract: 1 pt per flag, max 3 pts. A flag never raises probability. | `model_vs_market` (>6 pts apart), `bookies_disagree`, `favourite_away`, `h2h_against`, `form_against`, `ps_contradicts`, `model_fit_poor`. |
| G5 | **Odds filters are settings, not scoring.** Drop a candidate if `odds < LEG_ODDS_MIN (1.05)` or `odds > LEG_ODDS_MAX (3.5)` or `p_cal < MIN_LEG_PROB (0.75)`. The old band 1.11–1.57 does not exist anymore. | |
| G6 | **Odds must be the bookmaker's real odds of that exact market/outcome.** If no bookmaker offers it → not bettable → drop. Never substitute Forebet's 1X2 odds. | |
| G7 | **One tip per match = the candidate with the highest `p_cal`** among those that pass G5. Tie (within 1 pt): higher odds, then higher EV. Store top-3 alternatives and the top-3 rejected-with-reason. | "most likely to occur" |
| G8 | **No safe pick is a valid answer.** If nothing passes → return `None` and say why. Never lower thresholds silently. | |
| G9 | **Slip:** choose legs (1 per match) maximising joint probability `Πp` with `Πodds` inside `[SLIP_ODDS_MIN, SLIP_ODDS_MAX]`; or exactly `FORCE_LEGS` legs. Always display joint P, risk = 1−P, EV = P·O−1. | |
| G10 | **Settlement per bookmaker rules**; void/push legs are removed from the slip and total odds are recomputed. | |

### Block list (veto, applies before any maths)
`friendly`, `exhibition`, youth (`U17…U23`, `youth`), `women`, team name ending in `W`/`II`/`B` (football & basketball only), `reserve`, `doubles` (tennis), low-tier `ITF`, esports/virtual, any status other than `Scheduled`, any record failing `validate_record()`.
**Known trap (found while building the demo):** a naive regex `\b(w|ii|b)\b` blocked the tennis player "B. Player". The suffix rule must match only at the **end of a team name** and must **not** apply to tennis.

---

## 1. FOOTBALL

**Inputs:** `p1, px, p2` (Forebet %), `avg` (average total goals), optional predicted score, form, H2H, positions.
**Candidate markets:** 1X2, Double Chance (1X, X2, 12), Draw No Bet, Over/Under 0.5–4.5, BTTS Yes/No, (Handicap when real bookmaker odds exist).

| ID | Rule |
|---|---|
| F1 | **Result markets are exact from Forebet:** `DC 1X = p1+px`, `X2 = px+p2`, `12 = p1+p2`, `DNB 1 = p1/(p1+p2)`, `DNB 2 = p2/(p1+p2)`. No adjustments. |
| F2 | **Goal markets:** fit `λ_home + λ_away = avg` so that a Poisson score grid reproduces `p1/px/p2` (grid search over the home share of goals). Over/Under and BTTS are read from that grid. Report `fit_err` (RMS gap to Forebet's 1X2). If `fit_err > 0.05` → flag `model_fit_poor` and lower trust in goal markets. |
| F3 | If `avg` is missing or invalid → disable all goal markets for that match. |
| F4 | Block list applies. Also block when `p1+px+p2` is not ≈100 (±3) or odds ≤1.0. |
| F5 | Flags: `favourite_away` (pick is an away win), `h2h_against`, `form_against`, `ps_contradicts` (predicted score contradicts the tip), `model_vs_market`. |
| F6 | **Settlement:** regular time only (90 min + stoppage; extra time and penalties ignored). DNB: draw → push/void leg. Postponed/abandoned → void unless the bookmaker settles it. |

### Football examples (from the demo run)

**F1 Bayern Munich vs Union Berlin** — Forebet 76/15/9, avg 3.7, λ = 2.78 / 0.93.
- Model: 1X = **91%**, 12 = 85%, DNB 1 = 0.76/0.85 = **89.4%**, 1 = 76%, Over 1.5 = 88.4%.
- The safest tips are rejected by G5, not by probability: `Over 0.5 (97.5%, odds 1.01)` and `1X (90.9%, odds 1.04)` are below `LEG_ODDS_MIN`.
- **Best tip: DNB 1, p = 89.4%, odds 1.06.** Alternatives: Over 1.5 (88.4% @1.07), 12 (85.1% @1.11).

**F2 Torino vs Udinese** — 36/33/31, avg 2.1 (balanced).
- No 1X2/DC/DNB market reaches 75% at acceptable odds. Only goal markets pass: **Over 0.5, 87.7% @1.08**; Under 3.5 83.9% @1.12.
- Lesson: for balanced matches the engine does **not** force a result tip. It may take a goals market, or return `None` if even that fails.

**F3 Real Madrid vs Al Nassr (Club Friendlies)** → `BLOCKED: friendly`. (Old engine gave this 95%.)

**F4 Brentford vs Burnley** — 55/25/20, avg 3.0. Bookmaker is much more confident in Over 1.5 than the model (model 80.1%, bookmaker 88.9%, gap > 6 pts).
- `model_vs_market` flag → −1 pt. `p_cal` = 0.5·80.1 + 0.5·88.9 − 1 = **83.5%**, odds 1.06, EV −11.5%.
- Lesson: a big disagreement is information. The blend moves toward the bookmaker, and the flag tells the user (and later the calibration job) that this pick is "contested".

**F5 Lyon W vs PSG W** → `BLOCKED: women`.

---

## 2. BASKETBALL

**Inputs:** `p_home` and `p_away` (Forebet %, no draw; **overtime included**), `avg` = predicted total points.
**Candidate markets:** Winner (incl. OT), Handicap (.5 lines only), Total points Over/Under.

| ID | Rule |
|---|---|
| B1 | **Winner** = Forebet probability directly. Normalise `p_home+p_away` to 100. |
| B2 | **Margin model:** `margin = home − away ~ Normal(mean, SD)`, `SD = 11.5`. Choose `mean = SD · z(p_home)` (inverse normal CDF) so the model reproduces the winner probability. Then `P(Home +L) = Φ((mean+L)/SD)`, `P(Away +L) = Φ((L−mean)/SD)`. Use half-point lines only (no push). |
| B3 | **Totals:** `total ~ Normal(avg, 16)`. Lines = nearest .5 to `avg + {−10, −5, 0, +5}`. `P(Over L) = 1 − Φ((L−avg)/16)`. |
| B4 | Block list applies (also preseason, women, U-leagues, 3x3). Not modelled because no data: rest days/back-to-back, injuries, rotation. Say so in `why`. |
| B5 | Handicap lines with a big cushion usually pay < 1.05 and are dropped by G5 — that is normal. |
| B6 | **Settlement:** overtime counts for Winner/Handicap/Totals ("incl. overtime" markets). Postponed/not completed → void. |

### Basketball examples

**B1 Real Madrid vs Zalgiris (Euroleague)** — 84/16, avg 165.
- `mean = 11.5 · z(0.84) = 11.4` points. Home +9.5 = **96.5%**, Home +5.5 = 93.0% — both at odds 1.01 → rejected (G5).
- **Best tip: Home Win, p = 84.0%, odds 1.12.**

**B2 Hornets vs Pacers (NBA)** — 49/51, avg 232 (toss-up).
- Winner is ~50% → fails `MIN_LEG_PROB`. The engine uses the spread instead: **Away +9.5, p = 80.2%, odds 1.18** (alt. Home +9.5 78.8% @1.20).
- Lesson: in a coin-flip game the safe tip is a *cushioned handicap*, never the winner.

---

## 3. TENNIS

**Inputs:** `p_player1` (Forebet %), `avg_games` (expected total games), `best_of` (3, or 5 for men's Grand Slams).
**Candidate markets:** Match winner, games handicap (±3.5), total games Over/Under.

| ID | Rule |
|---|---|
| T1 | **Winner** = Forebet probability. |
| T2 | **Games-difference model:** `diff ~ Normal(mean, SD_d)`, `SD_d = 4.5` (best-of-3) / `6.0` (best-of-5), `mean = SD_d · z(p1)`. `P(P1 +L) = Φ((mean+L)/SD_d)`, `P(P2 +L) = Φ((L−mean)/SD_d)`. |
| T3 | **Total games:** `Normal(avg_games, SD_g)`, `SD_g = 4.0` (bo3) / `5.5` (bo5). Lines = nearest .5 to `avg_games + {−3, 0, +3}`. |
| T4 | Block: doubles, ITF/low-tier, exhibitions, status ≠ Scheduled, unknown `best_of`. |
| T5 | **Lopsided-match veto:** if the favourite has ≥ 85% → remove all `Over … games` candidates. A big mismatch finishes in few games, but the independent Normal model does not know that p and total games are correlated. |
| T6 | **Settlement (verify with the bookmaker's T&C):** walkover before play → void. Retirement after the match started → Winner usually settles for the opponent; games totals/handicap usually void. Implement as configurable per-bookmaker rules. |
| T7 | Not modelled (no data): surface, fatigue, injuries, head-to-head on surface. Note in `why`. |

### Tennis examples

**T1 J. Sinner vs Q. Qualifier** — 91/9, avg 19.5 games, best-of-3.
- `mean_game_diff = 4.5 · z(0.91) = 6.0`. P1 Win = 91.0% (odds 1.04 → rejected), P1 +3.5 games = 98.2% (odds 1.01 → rejected).
- T5 removes every Over. **Best tip: Under 22.5 games, p = 77.3%, odds 1.22.**
- Lesson: the strongest-probability tips in lopsided matches are often unbettable because the odds are too small; the engine falls to the next-best market instead of lowering `LEG_ODDS_MIN`.

**T2 A. Player vs B. Player** — 55/45, avg 22.5 → **P1 +3.5 games, 81.7% @1.15**. (This example caught the "B." regex bug above.)

**T3 Duo A vs Duo B (Doubles)** → `BLOCKED: doubles`.

---

## 4. FROM PICKS TO A SLIP (demo day)

Seven legs survived (one per match): Bayern DNB 1 (89.4% @1.06), Torino Over 0.5 (87.7% @1.08), Real Madrid Home Win (84.0% @1.12), Brentford Over 1.5 (83.5% @1.06), A. Player P1 +3.5 games (81.7% @1.15), Hornets Away +9.5 (80.2% @1.18), Sinner Under 22.5 games (77.3% @1.22).

**AUTO mode (odds 1.85–2.50, lowest risk first):**
| # | Legs | Total odds | Joint P | Risk | EV |
|---|---|---|---|---|---|
| 1 | 4 (Real Madrid, Hornets, Sinner, A. Player) | 1.85 | 42.6% | 57.4% | −21.0% |
| 2 | 5 | 1.90 | 39.8% | 60.2% | −24.6% |
| 3 | 5 | 1.97 | 38.1% | 61.9% | −25.2% |

**FORCE_LEGS = 5:** best 5 legs → odds 1.56, joint P 45.0%, with a warning "odds nje ya lengo".

### What the demo teaches (the AI and the owner must both understand this)
1. **"Most likely" is not "profitable".** In the demo every pick has EV ≈ −5% (the bookmaker margin) because the synthetic odds contain no mispricing. Real edge only exists where calibrated `p_cal` is above the bookmaker's devigged probability. The engine must show EV and never describe low-odds picks as "free money".
2. **Legs multiply risk and margin.** Four legs at ~80% each give a joint probability of ~43%; EV falls from −5% per leg to −21% for the slip. The slip builder must therefore show joint P first, and prefer fewer legs when they reach the odds range with higher P.
3. **Independence is an assumption.** Legs from the same league/day/team can be correlated; apply the haircut in the spec (Section 6) and say so in the UI.
4. **High probability + tiny odds is common.** Most of the safest tips are removed by `LEG_ODDS_MIN`. If the owner wants those included, he must lower the setting consciously; the engine must not do it.

---

## 5. TEST CASES THE AI MUST ADD (copy from `rules_demo.py` asserts)

```python
# G1 / F1: no inflation
assert abs(football_model(57,30,13,3.0)[0]["1X"] - 0.87) < 1e-9   # Liverpool: 87%, NOT 98%
assert abs(football_model(76,15,9,3.7)[0]["1X"] - 0.91) < 1e-9
# devig sums
assert abs(sum(devig([1.5,3.8,6.0])) - 1) < 1e-9
# blocks
assert blocked(dict(sport="football", league="Club Friendlies", home="A", away="B", status="Scheduled"))
assert blocked(dict(sport="football", league="Div 1", home="Lyon W", away="PSG W", status="Scheduled"))
assert not blocked(dict(sport="tennis", league="ATP 250", home="A. Player", away="B. Player", status="Scheduled"))
# basketball margin model reproduces winner probability
m,_,_ = basketball_model(84, 165); assert abs(m["Home Win"] - 0.84) < 1e-9
# tennis lopsided veto: no "Over" tip when favourite >= 85%
# slip: total odds within range, no duplicate matches, joint P == product of legs
```
Add per-sport tests for: odds below `LEG_ODDS_MIN` rejected; `None` returned when nothing passes; tie-break picks the higher odds within 1 pt; FORCE_LEGS warning when out of range; settlement of DNB draw (push), basketball OT, tennis retirement.

## 6. WHAT THE DEMO DELIBERATELY DOES NOT DO
- No scraping, no real bookmakers, no database (see the implementation spec).
- Brute-force slip search (fine for ~12 legs; production uses DP/beam search).
- Constants (SDs, W_MODEL, thresholds) are starting values. **They must be tuned on settled history** (backtest + calibration, spec Section 8), never trusted blindly.

## Runtime addendum — daily-coverage changes

This section supersedes the candidate-generation parts of G5/G6 above where they conflict with the current `engine.py`:

- Football goal markets can now use `goalsavg`; if absent, they fall back to the projected score total, then to the two teams' season scoring averages when both exist. They include match totals and each team's Over/Under 0.5 and 1.5 goals.
- Fitted home/away goal expectations are gently rebalanced with the teams' scoring averages, recent form and a small home-field factor. Form, standings rank, H2H and projected score can add directional risk flags; they only reduce the selected candidate's confidence. H2H and form are not treated as proof.
- Missing an exact bookmaker line no longer prevents the model from producing an analysis candidate. If exact bookmaker-priced candidates exist, the engine prefers those. Otherwise a model-only candidate may enter the pick pool, but the worker must still verify its market and live odds before it can enter a slip. The inverse of model probability is **not** treated as bookmaker odds.
- Uncalibrated confidence is capped at 95%, rather than displayed as certainty. Adaptive thresholds actually attempted are reported accurately (normally 80%, then 75%, then 70% if needed to seek three picks).
- Minimum individual bookmaker odds default is now **1.01** (not 1.05), so genuinely low-priced markets are not filtered out. Default slip odds target is **1.50–1.80** (instead of the older 1.85–2.50 example), matching the requested lower-return target. It remains a target range, not a promise that a slip will exist; only bookmaker-verified odds can be used.
- Daily diversity caps now allow up to 10 `Total Goals` and 10 `Team Goals` candidates, so the old cap of three does not block a 10-match totals-heavy day.

These changes improve coverage; they do not guarantee a fixed number of valid bets, profitability, or match outcomes. If a market is not offered by the bookmaker, it remains an analysis-only candidate and must not be placed in a slip.
