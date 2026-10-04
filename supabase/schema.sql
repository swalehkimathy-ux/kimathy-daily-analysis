-- Kimathy Daily Analysis — Supabase/PostgreSQL schema
-- Run this in the Supabase SQL editor. The browser app is read-only; the daily
-- automation uses the service-role key stored in GitHub Actions secrets.

create extension if not exists pgcrypto;

create table if not exists public.daily_fixtures (
  id uuid primary key default gen_random_uuid(),
  sport_type text not null check (sport_type in ('football', 'basketball', 'tennis')),
  match_name text not null,
  match_time timestamptz not null,
  market_name text not null,
  picked_odds numeric(5,2) not null check (picked_odds > 1.00),
  confidence_score numeric(5,2) not null check (confidence_score >= 0 and confidence_score <= 100),
  status text not null default 'pending' check (status in ('pending', 'win', 'loss', 'void')),
  analysis_note text,
  source text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Allows the automation to upsert a refreshed price/score for the same selection.
create unique index if not exists uq_daily_fixtures_selection
  on public.daily_fixtures (sport_type, match_name, match_time, market_name);
create index if not exists idx_fixtures_sport_status
  on public.daily_fixtures (sport_type, status);
create index if not exists idx_fixtures_match_time
  on public.daily_fixtures (match_time);

create table if not exists public.daily_accumulators (
  id uuid primary key default gen_random_uuid(),
  analysis_date date not null unique,
  status text not null default 'no_ticket' check (status in ('ready', 'no_ticket')),
  total_odds numeric(8,4) not null default 1.0000 check (total_odds >= 1.0000),
  target_min numeric(5,2) not null default 1.50,
  target_max numeric(5,2) not null default 1.90,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.daily_accumulator_legs (
  id uuid primary key default gen_random_uuid(),
  accumulator_id uuid not null references public.daily_accumulators(id) on delete cascade,
  fixture_id uuid not null references public.daily_fixtures(id) on delete cascade,
  leg_order integer not null check (leg_order > 0),
  odds_at_build numeric(5,2) not null check (odds_at_build > 1.00),
  score_at_build numeric(5,2) not null check (score_at_build >= 0 and score_at_build <= 100),
  created_at timestamptz not null default now(),
  unique (accumulator_id, leg_order),
  unique (accumulator_id, fixture_id)
);

-- The client needs only public read access. There are deliberately no anon write policies.
alter table public.daily_fixtures enable row level security;
alter table public.daily_accumulators enable row level security;
alter table public.daily_accumulator_legs enable row level security;

drop policy if exists "public can read daily fixtures" on public.daily_fixtures;
create policy "public can read daily fixtures"
  on public.daily_fixtures for select to anon, authenticated using (true);

drop policy if exists "public can read daily accumulator" on public.daily_accumulators;
create policy "public can read daily accumulator"
  on public.daily_accumulators for select to anon, authenticated using (true);

drop policy if exists "public can read accumulator legs" on public.daily_accumulator_legs;
create policy "public can read accumulator legs"
  on public.daily_accumulator_legs for select to anon, authenticated using (true);

grant select on public.daily_fixtures, public.daily_accumulators, public.daily_accumulator_legs to anon, authenticated;

comment on table public.daily_fixtures is 'Daily candidate fixtures and the market/odds/heuristic score used by Kimathy.';
comment on column public.daily_fixtures.confidence_score is '0–100 heuristic ranking score; not a calibrated event probability.';
comment on table public.daily_accumulators is 'One daily optimized accumulator record per analysis date.';
comment on table public.daily_accumulator_legs is 'Ordered fixture legs captured when the daily accumulator was built.';
