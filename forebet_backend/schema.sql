-- ═══════════════════════════════════════════════════════════════════════
-- KIMATHY96 PICKS — DATABASE SETUP (Supabase)
-- Hatua kwa hatua: Nakili sehemu MOJA kwa moja kwenye Supabase SQL Editor.
-- Jeura: Dashboard → SQL Editor → New query → nakili → Run
-- ═══════════════════════════════════════════════════════════════════════

-- ─── HATUA 1: day_cache (kumbukumbu ya siku zilizoshachotwa) ─────────────
-- Engine ikikumbuka: "siku hii imeshachotwa" — inatumia data ile-ile bila
-- kurugia Forebet. "Siku ikishabadilika" (midnight) → cache inajifuta.
create table if not exists public.day_cache (
    day            date        primary key,
    scraped_at     timestamptz not null default now(),
    match_count    int         not null default 0,
    engine_version text        not null default 'smart-engine v0.2',
    notes          text
);

-- ─── HATUA 2: matches (mechi zote za Forebet zilizochotwa) ───────────────
create table if not exists public.matches (
    id            bigint generated always as identity primary key,
    day           date        not null references public.day_cache(day) on delete cascade,
    sport         text        not null check (sport in ('football','basketball','tennis')),
    league        text,
    time_eat      text,                                 -- "20:00"
    home          text        not null,
    away          text        not null,

    p1            smallint,                             -- Forebet prob %
    px            smallint,
    p2            smallint,
    ps_home       smallint,                             -- Predicted score
    ps_away       smallint,
    avg_total     numeric(5,2),                         -- Avg goals/points/games
    kelly         numeric(6,3),                         -- Kelly ya Forebet
    odd1          numeric(6,2),
    oddx          numeric(6,2),
    odd2          numeric(6,2),
    status        text        default 'Scheduled',

    h2h           text,                                 -- "10 meetings: A 6W-2D-2L"
    avg_h         numeric(4,2),                         -- GF/GP ya home
    avg_a         numeric(4,2),
    form_home     jsonb,                                -- ["w","w","d",...]
    form_away     jsonb,
    home_pos      text,
    away_pos      text,

    final_home    smallint,                             -- RESULTS (baada ya mechi)
    final_away    smallint,
    url           text,
    raw           jsonb,                                -- backup ya data zote za ajabu

    created_at    timestamptz default now(),

    unique(day, sport, home, away)                      -- hakuna copy mbili
);

-- ─── HATUA 3: picks (tips zilizochaguliwa na SMART ENGINE) ───────────────
create table if not exists public.picks (
    id            bigint generated always as identity primary key,
    day           date        not null references public.day_cache(day) on delete cascade,
    sport         text        not null check (sport in ('football','basketball','tennis')),
    league        text,
    time_eat      text,
    home          text        not null,
    away          text        not null,

    market        text        not null,                 -- 1X2 / Double Chance / Total Goals / BTTS / Handicap
    tip           text        not null,                 -- "1X" / "Over 1.5" / "P1"
    conf          smallint    not null,                 -- confidence ya engine
    forebet       smallint    not null,                 -- prob ya msingi ya Forebet
    adj           smallint,                             -- +/− points za rules
    odd           numeric(6,2),
    rank          smallint,
    why           jsonb,                                -- ["H2H imara...", ...]
    decision      text,

    result        text        default 'pending'
                  check (result in ('pending','win','loss','push','void','unknown')),
    final_score   text,
    settled_at    timestamptz,

    engine_version text       not null default 'smart-engine v0.2',
    created_at    timestamptz default now(),

    unique(day, home, away, market, tip)
);

-- ─── HATUA 4: view ya statistics (kupima ubora wa engine) ────────────────
create or replace view public.engine_stats as
select
    market,
    sport,
    count(*)                                       as total,
    count(*) filter (where result = 'win')         as wins,
    count(*) filter (where result = 'loss')        as losses,
    round(100.0 * count(*) filter (where result = 'win')
        / nullif(count(*) filter (where result in ('win','loss')), 0), 1) as hit_pct,
    round(avg(conf)::numeric, 1)                   as avg_conf
from public.picks
group by market, sport
order by total desc;

-- ─── HATUA 5: indexes (speed) ────────────────────────────────────────────
create index if not exists idx_matches_day    on public.matches(day);
create index if not exists idx_picks_day      on public.picks(day);
create index if not exists idx_picks_result   on public.picks(result);
create index if not exists idx_picks_market   on public.picks(market);

-- ─── HATUA 6: RLS — hakuna anon access; worker pekee hutumia service_role ─
alter table public.day_cache enable row level security;
alter table public.matches    enable row level security;
alter table public.picks      enable row level security;

-- Hakuna SELECT/INSERT/UPDATE policy ya anon au authenticated kwa app hii ya desktop.
-- WORKER hutumia SERVICE_ROLE KEY upande wa PC (bypasses RLS); usiiweke kwenye frontend/APK.

-- ─── HATUA 7: maombi ya kawaida (ku-reference baadaye) ────────────────────
-- 1) Tips za leo:
--    select * from picks where day = '2026-10-27' order by rank;
-- 2) Matokeo ya engine kwa soko:
--    select * from engine_stats;
-- 3) Mechi zikahitaji trace (bado 'pending' lakini siku imepita):
--    select * from picks where result = 'pending' and day < current_date;

-- ═══ IMEMALIZIKA ✓ — Unapokwishaweka, nirudie na tutenge worker ───
