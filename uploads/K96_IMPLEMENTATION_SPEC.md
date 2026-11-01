# K96 PICKS — IMPLEMENTATION SPEC (hand this whole file to the AI that edits the code)

Owner language: Swahili. **Keep all user-facing UI text, log messages and code comments in Swahili** (existing style).
This spec is written in English so the coding AI follows it precisely.

---

## 0. READ THIS FIRST (rules for the coding AI)

1. Work **phase by phase** (Section 9). Finish a phase, run its tests, show results, then continue. Do not rewrite the whole project at once.
2. Never print, log, commit or paste secrets. `.env.local` values must never appear in output, zips, logs or the UI.
3. Do not break the existing pipeline: `scraper.collect -> engine.analyze_day -> picks.run -> worker.cmd_run/cmd_settle -> gui_server -> index.html`. Existing test `forebet_picks_app/_tests/test_msingi.py` must be **updated, not deleted**, when behaviour intentionally changes.
4. The UI and output must **never claim guaranteed or "99.8%" winning**. It must show honest numbers: per-leg probability, **joint probability of the whole slip**, and total odds.
5. Every number the engine shows as "probability" must be a real probability (0–100%) that is **calibrated** against settled history (Phase 6). Until enough history exists, label it "estimated".
6. Add unit tests for every new function. A phase is "done" only when its acceptance criteria (listed per phase) pass.

---

## 1. WHAT THE OWNER WANTS (plain intent)

- A very professional betting assistant. Data source: Forebet scraping, plus **bookmaker odds/opinions** (Betway TZ, betPawa TZ).
- The **Smart Engine** (heart of the app) analyses each match and, **per match, picks the single tip that is most likely to occur** (highest calibrated probability), across all markets (1X2, Double Chance, Draw No Bet, Totals, BTTS, Handicap, Winner).
- The engine then builds a **betslip with any number of matches (even 10 or more)** whose overall risk is as low as possible.
- Daily target total odds: **default 1.85 – 2.50** (configurable). The number of legs is NOT fixed: it can be 1, 2, 3 … 10+ depending on what gives the lowest risk, or the user can force a number of legs.
- **Remove the hard-coded favourite odds band 1.11–1.57.** Odds limits must be flexible user settings (Section 5.4), not a scoring rule.
- Scraping data accuracy target: **≥ 99.8 % of stored fields correct**, measured (Section 4.3). (Outcome accuracy of matches can never be 99.8 %; never promise it.)

---

## 2. CURRENT CODE MAP (what exists)

```
forebet_picks_app/
  scraper.py   (850 lines)  Forebet scraping: football JSON getrs.php, basketball/tennis DOM, enrich H2H
  engine.py    (424)        SMART ENGINE v0.2: adjustments() rules, markets, analyze_match, analyze_day_full
  picks.py     (174)        run(): collect -> engine -> Excel + @PICKS json + copy_text
  bookie.py    (267)        betPawa verification (+ fallback orchestration verify_pick)
  betway.py    (245)        Betway TZ verification (primary)
  _tests/test_msingi.py     synthetic E2E test (mock data only)
forebet_backend/
  worker.py    (423)        Supabase client sb(), run/settle/status/daemon, settle_pick()
  gui_server.py(425)        local HTTP API for the GUI (uses worker.sb with service role)
  index.html                GUI (5 tabs)  | electron/ wrapper | schema.sql | *.bat
forebet_scraper/scraper.py  (846)  DUPLICATE, already diverged from forebet_picks_app/scraper.py
```

---

## 3. CONFIRMED PROBLEMS (found by reading + running the code)

### 3.1 Engine (`engine.py`)
| # | Problem | Evidence | Required fix |
|---|---|---|---|
| E1 | **No slip builder.** Engine returns 3–10 independent picks; nothing aims at a total-odds target or minimises combined risk. | `analyze_day_full` only sorts by conf and applies `CAPS` | Build `slip.py` (Section 6) |
| E2 | **Confidence double counting.** `conf = base probability + sum(adjustments)`. Form, H2H, home advantage, league position are already inside Forebet's probability. Example in test: Liverpool Forebet 57 → DC 1X = 87 → +28 → **98%**. | `dc_market`, `analyze_match`, test output | Replace with probability model (Section 5). Rules become veto flags / tiny tie-breakers (cap total ±3 points). |
| E3 | `conf` is a score, not a probability; never calibrated. | comment in WARAKA doc, Phase 5/6 never done | Calibrate (Section 8) |
| E4 | **Odds band 1.11–1.57** gives +6 and uses the *1X2 favourite's* odds even for Totals/BTTS/DC picks (wrong odds for the chosen market). | `ODDS_BAND`, lines ~300–309 | Delete rule. Use real bookmaker odds **of the chosen market** (Section 5.4) |
| E5 | Bookmaker odds are used **only to verify "bettable"**; never for probability or value. | `bookie.verify_pick`, `betway.verify_pick_betway` | Use devigged bookmaker probabilities as a model input (Section 5.2) |
| E6 | Friendly matches only get −8 but still pass (Real Madrid friendly → 95%). | test output | Hard-block friendlies (like youth/women) unless owner enables a setting |
| E7 | Market choice uses a fixed `pref` priority (DC=4, DNB=3, …) before probability, so the **most probable tip is not necessarily chosen**. | `best = max(cands, key=(pref, conf))` | Choose max calibrated probability (Section 5.5) |
| E8 | Goals/BTTS use a Poisson with independence; `Over 0.5` hack. Probabilities are approximate. | `goals_market`, `btts_market` | Use bivariate/Dixon-Coles style or at least blend with bookmaker prob; keep Poisson as fallback |
| E9 | Basketball/Tennis: Winner only, gate `fb < 50`. Settlement of these sports is not implemented. | `analyze_match`, `worker.settle_pick` | Add settlement + (optional) totals later |
| E10 | `MIN_CONF` and `TIMEZONE_OFFSET_EAT` in `.env.local` are **never read**; GUI hard-codes `engine.MIN_CONF = 80` (gui_server.py lines ~96, ~294). | grep | Single config module (Section 7.3) |

### 3.2 Bookmaker layer (`bookie.py`, `betway.py`)
| # | Problem | Evidence | Required fix |
|---|---|---|---|
| B1 | **Wrong-match bug (verified).** `_sim()` uses overlap coefficient with `min(len)`. `"Inter"` vs `"Inter Miami"` = **1.00**, `"Barcelona"` vs `"Barcelona SC"` = 1.00, `"Lyon"` vs `"Lyon W"` = 1.00, and `_find_event` returned the wrong event. No kickoff-time or league check. | executed in sandbox | New matcher (Section 4.2) |
| B2 | Betway day index uses `BetBook/Highlights` with `Take=50`, loop capped at `skip <= 300`: may **not list all events**, causing false "NOT BETTABLE". | betway.py `day_index` | Verify coverage; add fallback search; log coverage ratio vs betPawa |
| B3 | Two copies of near-identical `_norm/_sim/_find_event`. | bookie.py / betway.py | One shared `matching.py` |
| B4 | Odds are fetched per pick, per run, with no snapshot stored → no closing-line value, no history. | — | Store `odds_snapshots` (Section 7) |

### 3.3 Scraper (`scraper.py`)
| # | Problem | Required fix |
|---|---|---|
| S1 | 18 `except` blocks, several `except Exception: pass` — silent data loss. | Replace with specific exceptions + logged counters |
| S2 | **No validation** of scraped fields (probabilities sum ≈ 100, odds > 1.0, valid date/time/timezone, non-empty teams, freshness). | Add `validate_record()` (Section 4.1) |
| S3 | Two diverged copies (`forebet_scraper/` and `forebet_picks_app/`). | Keep one, delete/redirect the other |

### 3.4 Learning/measurement
- Settlement exists for football only. No backtest. No calibration. Without these nobody can state a real hit-rate.

---

## 4. PHASE 1–2: SCRAPER VALIDATION + MATCHING

### 4.1 `validate_record(rec, sport)` — new, in `scraper.py` (or `validation.py`)
Return `(ok: bool, problems: list[str])`. A record that fails is **dropped from engine input and counted** (never silently fixed).
Rules (football):
- `home`, `away` non-empty, different, length 2–60, no HTML remnants (`<`, `&nbsp;`).
- `p` = [p1,px,p2]: all ints 0–100, `abs(sum-100) <= 3` (Forebet rounding).
- `od` odds: each `>= 1.01` and `<= 200`; if both `p` and `od` exist, `1/od_i` ordering must be consistent with `p` ordering for the top side (else flag `odds_conflict`, keep but mark low-trust).
- `ps` predicted score: ints 0–15. `avg`: 0–8 for football; basketball 120–300; tennis 12–60.
- `dt` timezone-aware, converted to EAT (UTC+3), date equals requested day (±1 for after-midnight matches), and kickoff not in the past by more than status allows.
- `status` in known set; if finished/live, flag `not_pre_match` and exclude from picks.
- `league` non-empty.
Return stats per run: `total, valid, dropped_by_reason{}`. Log them. Expose in GUI LOG tab.

### 4.2 `matching.py` — shared matcher (replaces `_sim/_find_event` copies)
Algorithm:
1. Normalise: unicode-fold, lowercase, remove punctuation, map aliases (`man utd`→`manchester united`, `psg`→`paris saint germain`, `inter`→`internazionale` …; keep alias table in `data/aliases.json`, extendable).
2. **Distinguishing tokens must match exactly**: `w`, `women`, `u17..u23`, `ii`, `b`, `reserves`, `sc`/`miami`/`city`/`united` style suffixes when the other side has them. Rule: if either side has a distinguishing token that the other lacks → **score 0**.
3. Name score = token Jaccard (not min-overlap) combined with `difflib.SequenceMatcher` ratio; threshold ≥ 0.80 per team.
4. **Kickoff time must be within ±20 minutes** (EAT). If either time unknown → require name score ≥ 0.92.
5. League/competition fuzzy match as tie-breaker; if two candidates remain within 0.03 of each other → **reject as ambiguous** (return `None`, log `ambiguous`). Never guess.
6. Return `(event, flipped, score, reason)`.
Tests (must pass): `Inter`≠`Inter Miami`, `Barcelona`≠`Barcelona SC`, `Lyon`≠`Lyon W`, `Arsenal`≠`Arsenal Tula`, `Man City`=`Manchester City`, `Bayern`=`Bayern Munich`, flipped tennis names, time mismatch rejects, ambiguous rejects.

### 4.3 Measuring "scraping accuracy 99.8 %"
Define: `accuracy = fields_correct / fields_checked` on an **audit sample** of ≥ 500 fields (teams, kickoff, p1/px/p2, odds, ps, avg) re-read from the live Forebet page by a second independent parser (or manual spot-check CSV). Add `audit.py` that samples N random matches from Supabase `matches`, re-fetches, compares, prints accuracy and each mismatch. Plus the automatic `valid/total` ratio from 4.1. Report both in the ENGINE STATS tab.

---

## 5. PHASE 3–4: PROBABILITY ENGINE (replaces additive confidence)

### 5.1 Model probability `p_model` per market
- 1X2 from Forebet `p`. DC = p1+px etc. (exact). DNB = p_fav/(p_fav+p_opp).
- Totals/BTTS/Handicap from a bivariate Poisson (or Dixon-Coles low-score correction) using `lambda_home, lambda_away` from `ps` + `avg` + `avg_h/avg_a` (existing `_lambda_split` is a start). Must reproduce 1X2 probabilities within ±3 pts (fit lambdas to p1/px/p2 when available).
- Basketball/Tennis: Winner from Forebet p, optionally Totals later.
- Do **not** add rule points to probability. See 5.6 for rules.

### 5.2 Market probability `p_market` (bookmaker opinion)
- For each bookmaker (Betway, betPawa) and each market, read **all outcomes of that market**, compute implied `1/odds`, **remove the margin** (proportional or Shin method): `p_i = (1/o_i) / Σ(1/o_j)`.
- Combine the two bookmakers by average (weights configurable; later weight by closing-line accuracy). If only one bookmaker has the match, use it and flag `single_source`.
- If the two bookmakers disagree by > 6 percentage points on the chosen outcome → flag `bookies_disagree` and lower rank (not hard block).
- Fetch **the whole market once per event** and cache it for the run (no re-fetch per candidate).

### 5.3 Final probability
```
p_final = w * p_model + (1 - w) * p_market        # default w = 0.5 until calibration data exists
p_cal   = calibrate(p_final)                       # isotonic/Platt fitted on settled picks (Phase 6); identity before
```
If `p_market` is missing, `p_final = p_model` and the pick is labelled `model_only` (lower trust, configurable penalty).

### 5.4 Odds settings (flexible, NOT scoring rules) — replaces `ODDS_BAND`
Delete `ODDS_BAND` and the +6/+2/−6 odds rules in `analyze_match`. Add to `config.py`:
```
LEG_ODDS_MIN   = 1.05   # ignore legs paying less (useless, e.g. Over 0.5 @1.01)
LEG_ODDS_MAX   = 3.50   # ignore very risky legs (None = no limit)
SLIP_ODDS_MIN  = 1.85
SLIP_ODDS_MAX  = 2.50
MAX_LEGS       = 12     # upper limit; user can set any number or "auto"
FORCE_LEGS     = None   # if integer N: build slip with exactly N legs
MIN_LEG_PROB   = 0.75   # drop candidate tips below this calibrated probability
BLOCK_FRIENDLY = True
```
All of these editable in the GUI SETTINGS tab and persisted (localStorage + Supabase `settings` table optional).
The odds used everywhere = **real bookmaker odds of the chosen market and outcome** (Betway first, betPawa fallback). If neither bookmaker offers the market, the candidate is **not bettable** and is dropped (do not use Forebet's 1X2 odds as a substitute).

### 5.5 Best tip per match (the core requirement)
For each match, build candidates across all markets (1X2, DC, DNB, Totals 0.5–4.5, BTTS, Handicap, Winner). For each candidate compute `p_cal`, `bk_odds` (real), `ev = p_cal*bk_odds - 1`.
Filter: bettable, `LEG_ODDS_MIN <= bk_odds <= LEG_ODDS_MAX`, `p_cal >= MIN_LEG_PROB`, not blocked, valid record.
**Select the candidate with the highest `p_cal`** (that is "the tip most likely to occur"). Tie-break (within 1 pt): higher `bk_odds`, then higher `ev`. Store the top-3 alternatives with reasons in `why` for transparency. One tip per match only.
Output per match: `{match, market, tip, p_cal, p_model, p_market, bk_odds, bookmaker, ev, flags[], why[]}`.

### 5.6 What to do with the old 10 rules (`adjustments()`)
- Keep as **veto/risk flags**, not additive points: friendly (block), youth/women (block), favourite away (flag), H2H against (flag), form against (flag), PS contradicts tip (flag), bookies disagree (flag).
- A flag may reduce the slip-builder score by at most a small fixed penalty (config `FLAG_PENALTY = 0.01` probability each, cap 0.03). It must never raise probability.
- Add lineup/rotation/injury flags **only if** a reliable data source is added later (do not invent).

### 5.7 Tests
- Liverpool example: Forebet 57/30/13 must give DC 1X `p_model = 0.87` (NOT 0.98).
- Man City vs Chelsea (40/32/28, avg 3.4) must not produce 85% for anything unless bookmakers support it.
- Fully offline unit tests with injected bookmaker markets (fixtures), no network.

---

## 6. PHASE 5: SLIP BUILDER (`slip.py`) — main missing feature

Input: one best candidate per match (Section 5.5), config (Section 5.4).
Definitions: leg i has probability `p_i` (calibrated) and odds `o_i`. Slip total odds `O = Π o_i`. **Joint probability** `P = Π p_i × corr_haircut` where `corr_haircut` = 0.98^(number of leg pairs with obvious correlation, e.g. same league same day or same team involved), default no correlation. **Risk = 1 − P.**

Optimisation: choose a subset S (size 1..MAX_LEGS, or exactly FORCE_LEGS) such that `SLIP_ODDS_MIN <= O <= SLIP_ODDS_MAX` and **P is maximised** (risk minimised).
Equivalent form: minimise `Σ −ln p_i` subject to `Σ ln o_i ∈ [ln MIN, ln MAX]`.
Implementation:
- Candidates ≤ ~80/day → **dynamic programming over discretised log-odds** (step 0.005) keeping best `Σ ln p` per (bucket, count) with back-pointers; or beam search (width 200). Deterministic, no randomness.
- Return the **top K slips (default 5)** ranked by P, with labels: `SAFEST`, `BALANCED`, `HIGHER_ODDS` (closest to upper odds bound).
- `FORCE_LEGS = N` mode: pick the N legs with highest `p_i` (subject to leg-odds limits), report `O` and `P` even when `O` is outside the odds range, and show a clear warning ("odds ya jumla X iko nje ya lengo").
- Never put two legs from the same match. Optional: max 2 legs per league.
- If no valid slip exists → return an explicit "hakuna slip salama leo" (no forced bad slip).
Display (GUI + Excel + copy text): each leg (time, match, market, tip, odds, p), total odds, **joint probability %**, risk %, expected value `P*O-1`, bookmaker used, flags. Add a plain line: "Kadiri legs zinavyoongezeka, uwezekano wa jumla unapungua."
Info for owner (important, show in UI help): every extra leg multiplies bookmaker margin and risk. A slip of 10 legs each 90% has joint probability ≈ 35%. The builder will therefore prefer fewer legs unless many low-odds legs give the highest P inside the odds range; this is intended.
Tests: slip total odds always inside range; P equals product of legs; no duplicate matches; deterministic output; FORCE_LEGS=10 returns 10 legs; empty input handled.

---

## 7. SUPABASE / ENVIRONMENT REVIEW

### 7.1 What was checked (without exposing values)
- `.env.local` has: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `MIN_CONF`, `TIMEZONE_OFFSET_EAT`.
- URL format valid (`https://<20 chars>.supabase.co`, no trailing slash). Both keys are well-formed JWTs, roles are correct (`service_role` and `anon`), **both belong to the same project as the URL**, expiry is far in the future, no stray quotes/spaces. The env file itself is structurally fine.
- A live connection could **not** be tested from the review sandbox (no internet). Owner must run the connection test (7.4).

### 7.2 Problems
| # | Problem | Fix |
|---|---|---|
| D1 | **Secret exposure**: `.env.local` (with the service-role key) is inside the uploaded Project.zip **and inside `K96_PICKS_PC_v1.8.zip`** (the distribution zip). | Owner: **rotate both keys in Supabase dashboard (Project Settings → API)**, update local `.env.local`. Code: exclude `.env.local` from all zips/builds (`K96_BUILD.bat`), add `.gitignore`, ship `.env.example` with empty values. |
| D2 | `load_env()` validation block ends with `pass` (dead code): wrong/placeholder keys give cryptic HTTP errors later. | Implement real validation: URL regex, JWT role check, ref matches URL, friendly Swahili error, exit code 2. |
| D3 | `MIN_CONF`, `TIMEZONE_OFFSET_EAT` unused; GUI hard-codes 80. | One `config.py` reading env + settings; remove hard-codes. |
| D4 | `picks`/`matches` have `on delete cascade` from `day_cache`. The design says the cache "inajifuta" at midnight — deleting a `day_cache` row **would delete settled picks (the learning history)**. | Change FK to `on delete restrict` (or drop FK) for `picks`; never delete `day_cache` rows that have settled picks. Add migration. |
| D5 | `engine_stats` view runs with owner rights (bypasses RLS). It exposes only aggregates, acceptable, but make it explicit. | `alter view public.engine_stats set (security_invoker = true);` or keep intentionally; document. |
| D6 | Schema lacks: bookmaker odds per pick, probabilities, EV, slips, odds snapshots, calibration. | Migration below. |
| D7 | `TEST_CONNECTION.bat` only checks that the URL answers; it never tests keys, RLS or tables. | Replace with `test_supabase.py` (7.4). |
| D8 | `picks.unique(day, home, away, market, tip)` lacks `sport`. Low risk, add for safety. | Include `sport`. |
| D9 | Basketball/Tennis results are not settled, so `engine_stats` for them stays empty. | Phase 6. |

### 7.3 Migration SQL (create `schema_v2.sql`; must be idempotent)
```sql
-- picks: new analytics columns
alter table public.picks
  add column if not exists p_model    numeric(5,4),
  add column if not exists p_market   numeric(5,4),
  add column if not exists p_final    numeric(5,4),
  add column if not exists p_cal      numeric(5,4),
  add column if not exists bk_odds    numeric(7,3),
  add column if not exists bookmaker  text,
  add column if not exists ev         numeric(7,4),
  add column if not exists flags      jsonb,
  add column if not exists model_version text;

-- keep settled history: replace cascade FK with restrict
alter table public.picks drop constraint if exists picks_day_fkey;
alter table public.picks add constraint picks_day_fkey
  foreign key (day) references public.day_cache(day) on delete restrict;

-- bookmaker odds snapshots (for value + closing-line analysis)
create table if not exists public.odds_snapshots (
  id bigint generated always as identity primary key,
  day date not null, sport text not null, home text not null, away text not null,
  bookmaker text not null, market text not null, outcome text not null,
  line numeric(5,2), odds numeric(7,3) not null, suspended boolean default false,
  taken_at timestamptz not null default now()
);
create index if not exists idx_odds_snap_day on public.odds_snapshots(day);

-- slips
create table if not exists public.slips (
  id bigint generated always as identity primary key,
  day date not null, label text not null,           -- SAFEST / BALANCED / HIGHER_ODDS
  legs smallint not null, total_odds numeric(8,3) not null,
  joint_prob numeric(6,5) not null, ev numeric(7,4),
  result text default 'pending' check (result in ('pending','win','loss','void')),
  settled_at timestamptz, engine_version text, created_at timestamptz default now()
);
create table if not exists public.slip_legs (
  id bigint generated always as identity primary key,
  slip_id bigint not null references public.slips(id) on delete cascade,
  pick_id bigint references public.picks(id) on delete set null,
  home text not null, away text not null, market text not null, tip text not null,
  odds numeric(7,3) not null, p_cal numeric(5,4),
  result text default 'pending' check (result in ('pending','win','loss','push','void'))
);

-- RLS: read-only for anon, write only via service role
alter table public.odds_snapshots enable row level security;
alter table public.slips          enable row level security;
alter table public.slip_legs      enable row level security;
create policy if not exists anon_read_slips on public.slips for select using (true);
create policy if not exists anon_read_slip_legs on public.slip_legs for select using (true);
-- odds_snapshots: no anon policy (private to the worker)

-- calibration view: hit rate by probability bucket
create or replace view public.calibration as
select width_bucket(p_cal, 0, 1, 20) as bucket, count(*) as n,
       round(avg(p_cal)::numeric, 3) as avg_pred,
       round((count(*) filter (where result='win'))::numeric
             / nullif(count(*) filter (where result in ('win','loss')),0), 3) as actual
from public.picks where result in ('win','loss') and p_cal is not null group by 1 order by 1;
```
(Adjust `create policy if not exists` to `drop policy if exists ...; create policy ...` if the Postgres version rejects it.)

### 7.4 `test_supabase.py` (replace `TEST_CONNECTION.bat` logic; the .bat just calls it)
Must check and print PASS/FAIL (never print keys):
1. env present + format valid (D2 rules).
2. `GET /rest/v1/picks?limit=1` with **service role** → 200.
3. Same with **anon** → 200 (read allowed).
4. `POST /rest/v1/picks` with **anon** → **401/403** (write must be denied).
5. All required tables/views exist (`day_cache, matches, picks, slips, slip_legs, odds_snapshots, engine_stats, calibration`).
6. Round trip: insert a test row with service role and delete it (use a marker day like `1999-01-01`, remove after).
7. Clock check: compare local EAT time vs `Date` header of the response (warn if skew > 120 s).

---

## 8. PHASE 6: SETTLEMENT, BACKTEST, CALIBRATION

1. `settle_pick` already covers football markets. Add Basketball (winner incl. OT) and Tennis (match winner; handle retirement/walkover as `void`). Add `settle_slip`: slip wins only if all non-void legs win; `push/void` legs are removed and total odds recomputed.
2. `backtest.py --from 2026-09-01 --to 2026-10-27`: replay stored `matches` (+ finals) through the engine in **walk-forward** mode (no future leakage). Output: number of picks, hit-rate overall/by market/by probability bucket, **Brier score**, **log loss**, calibration table, slip hit-rate and ROI at stored odds (if snapshots exist).
3. `calibration.py`: fit isotonic regression (or Platt scaling) on settled picks when n ≥ 300; store parameters in `data/calibration.json`; `calibrate()` uses it; refit weekly by the daemon.
4. Daemon (`worker.py daemon`): 00:00 scrape + run, **06:00 and 12:00 odds refresh**, 01:00 settle yesterday, weekly calibration refit.
5. GUI RESULTS/ENGINE STATS tabs: add calibration chart (predicted vs actual), slip history, Brier score.
**Acceptance:** after ≥ 30 settled days, in every probability bucket |avg_pred − actual| ≤ 5 pts, or the UI shows "bado haijakalibishwa vizuri". Report honestly even if bad.

---

## 9. PHASES (do in this order; show test output after each)

| Phase | Work | Done when |
|---|---|---|
| 1 | `validation.py`, replace silent excepts, dedupe scraper copies, `config.py`, real `load_env` validation, `.gitignore`, `.env.example`, exclude `.env.local` from build zips, `test_supabase.py` | validation unit tests + Supabase test pass; stats printed per run |
| 2 | `matching.py` shared by bookie/betway; alias table; time/league checks; ambiguity rejection | all Section 4.2 tests pass; old bug cases fixed |
| 3 | Bookmaker market fetch (full outcome set), devig, `odds_snapshots` storage, coverage log (Betway vs betPawa) | fixture tests pass; coverage ratio reported |
| 4 | Probability engine (Section 5), delete `ODDS_BAND`, best tip per match, flags instead of points, hard-block friendlies, update `test_msingi.py` | Liverpool 1X = 87% not 98%; no odds-band code left; best-tip tests pass |
| 5 | `slip.py` + GUI "SLIPS" tab + Excel/copy output + settings (odds range, legs count, force legs) | slip tests pass; owner can request 10-leg slip |
| 6 | Settlement for all sports/slips, backtest, calibration, daemon jobs, new GUI charts | backtest report produced; calibration table shown |
| 7 | Polish: error messages in Swahili, README, `K96_BUILD.bat` (no secrets inside), versioning `smart-engine v0.3` | build artefact contains no `.env.local` |

---

## 10. DEFINITION OF DONE (global)

- `python forebet_picks_app/_tests/test_msingi.py` and all new tests pass offline.
- No leftover references to `ODDS_BAND`, `1.11`, `1.57` in code (grep).
- No secrets in repo/zips (grep for `eyJ` and `service_role` returns nothing in shipped files).
- UI never displays a guarantee; always shows joint probability and risk next to total odds.
- `engine_version` stored on every pick and slip.
- A short `CHANGELOG.md` listing what changed per phase and any known limitation.

## 11. KNOWN LIMITS (be honest in the UI/README)

- Forebet + two bookmakers are limited data. No lineup/injury/market-movement data → some risk cannot be modelled.
- Scraping can break when Forebet or bookmaker sites change; validation is the early-warning system.
- Calibration needs history; before that, probabilities are estimates.
- Betting always carries risk of loss; bankroll limits should be shown in the UI.
