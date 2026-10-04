-- TEMPORARY UI TEST DATA ONLY.
-- These are fictional fixtures and odds, not a real sports slate.
-- Run this in Supabase SQL Editor to test that the dashboard can read and
-- optimize rows from daily_fixtures. Remove them afterwards using the cleanup
-- statement in the README or the standalone cleanup file.

with test_rows as (
  select
    'football'::text as sport_type,
    'TEST ONLY — Harbor City FC vs Mlimani Rovers'::text as match_name,
    (((now() at time zone 'Africa/Dar_es_Salaam')::date + time '17:00') at time zone 'Africa/Dar_es_Salaam') as match_time,
    'Double Chance · 1X'::text as market_name,
    1.12::numeric(5,2) as picked_odds,
    93.40::numeric(5,2) as confidence_score,
    'TEST ONLY — fictional teams and price; illustrative top-three-home-side profile.'::text as analysis_note
  union all
  select
    'tennis',
    'TEST ONLY — N. Okafor vs L. Moreau',
    (((now() at time zone 'Africa/Dar_es_Salaam')::date + time '17:30') at time zone 'Africa/Dar_es_Salaam'),
    'Match Winner · N. Okafor',
    1.14::numeric(5,2),
    91.20::numeric(5,2),
    'TEST ONLY — fictional players and price; illustrative preferred-surface profile.'
  union all
  select
    'basketball',
    'TEST ONLY — Dar Falcons vs Dodoma Titans',
    (((now() at time zone 'Africa/Dar_es_Salaam')::date + time '18:00') at time zone 'Africa/Dar_es_Salaam'),
    'Moneyline · Home Win',
    1.13::numeric(5,2),
    89.80::numeric(5,2),
    'TEST ONLY — fictional teams and price; illustrative home-form profile.'
  union all
  select
    'football',
    'TEST ONLY — Kilimanjaro Athletic vs Coastal United',
    (((now() at time zone 'Africa/Dar_es_Salaam')::date + time '18:30') at time zone 'Africa/Dar_es_Salaam'),
    'Over 0.5 Goals',
    1.11::numeric(5,2),
    88.90::numeric(5,2),
    'TEST ONLY — fictional teams and price; illustrative low-goal-line profile.'
)
insert into public.daily_fixtures (
  sport_type, match_name, match_time, market_name,
  picked_odds, confidence_score, status, analysis_note, source, updated_at
)
select
  sport_type, match_name, match_time, market_name,
  picked_odds, confidence_score, 'pending', analysis_note, 'interface-test', now()
from test_rows
on conflict (sport_type, match_name, match_time, market_name)
do update set
  picked_odds = excluded.picked_odds,
  confidence_score = excluded.confidence_score,
  status = 'pending',
  analysis_note = excluded.analysis_note,
  source = 'interface-test',
  updated_at = now();

-- Expected result when the dashboard refreshes: four TEST ONLY rows and a
-- combined decimal odds total close to 1.60 (1.60149024 before display rounding).
