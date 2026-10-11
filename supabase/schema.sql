-- Kimathy Daily Analysis — private Supabase/PostgreSQL schema.
-- The GitHub Actions runner writes using the service-role key. The browser is
-- sign-in-only and receives read access only for an explicitly allowlisted user.

create extension if not exists pgcrypto;

create table if not exists public.daily_fixtures (
  id uuid primary key default gen_random_uuid(),
  sport_type text not null check (sport_type in ('football', 'basketball', 'tennis')),
  match_name text not null,
  home_team text,
  away_team text,
  match_time timestamptz not null,
  market_name text not null,
  market_key text,
  market_point numeric(8,3),
  selection_name text,
  selection_side text,
  event_id text,
  sport_key text,
  competition text,
  odds_updated_at timestamptz,
  picked_odds numeric(5,2) not null check (picked_odds > 1.00),
  confidence_score numeric(5,2) not null check (confidence_score >= 0 and confidence_score <= 100),
  status text not null default 'pending' check (status in ('pending', 'win', 'loss', 'void')),
  analysis_note text,
  source text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.daily_fixtures add column if not exists home_team text;
alter table public.daily_fixtures add column if not exists away_team text;
alter table public.daily_fixtures add column if not exists market_key text;
alter table public.daily_fixtures add column if not exists market_point numeric(8,3);
alter table public.daily_fixtures add column if not exists selection_name text;
alter table public.daily_fixtures add column if not exists selection_side text;
alter table public.daily_fixtures add column if not exists event_id text;
alter table public.daily_fixtures add column if not exists sport_key text;
alter table public.daily_fixtures add column if not exists competition text;
alter table public.daily_fixtures add column if not exists odds_updated_at timestamptz;

create unique index if not exists uq_daily_fixtures_selection
  on public.daily_fixtures (sport_type, match_name, match_time, market_name);
create index if not exists idx_fixtures_sport_status
  on public.daily_fixtures (sport_type, status);
create index if not exists idx_fixtures_match_time
  on public.daily_fixtures (match_time);
create index if not exists idx_fixtures_market_status_time
  on public.daily_fixtures (market_key, status, match_time);

create table if not exists public.daily_accumulators (
  id uuid primary key default gen_random_uuid(),
  analysis_date date not null unique,
  status text not null default 'no_ticket' check (status in ('ready', 'no_ticket')),
  total_odds numeric(8,4) not null default 1.0000 check (total_odds >= 1.0000),
  target_min numeric(5,2) not null default 1.50,
  target_max numeric(5,2) not null default 1.90,
  settlement_status text not null default 'pending'
    check (settlement_status in ('pending', 'won', 'lost', 'void', 'not_applicable')),
  settled_at timestamptz,
  settled_total_odds numeric(8,4),
  net_units numeric(10,4),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.daily_accumulators add column if not exists settlement_status text not null default 'pending';
alter table public.daily_accumulators add column if not exists settled_at timestamptz;
alter table public.daily_accumulators add column if not exists settled_total_odds numeric(8,4);
alter table public.daily_accumulators add column if not exists net_units numeric(10,4);
update public.daily_accumulators
set settlement_status = 'not_applicable'
where status = 'no_ticket' and settlement_status = 'pending';

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'daily_accumulators_settlement_status_check'
      and conrelid = 'public.daily_accumulators'::regclass
  ) then
    alter table public.daily_accumulators
      add constraint daily_accumulators_settlement_status_check
      check (settlement_status in ('pending', 'won', 'lost', 'void', 'not_applicable'));
  end if;
end $$;

create index if not exists idx_accumulator_history
  on public.daily_accumulators (analysis_date desc, status, settlement_status);

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

create index if not exists idx_accumulator_legs_fixture
  on public.daily_accumulator_legs (fixture_id);

-- Explicit single-user allowlist. Create the Auth user first, then run the
-- separate supabase/authorize-owner-template.sql with that user's email.
create table if not exists public.kimathy_allowed_users (
  user_id uuid primary key references auth.users(id) on delete cascade,
  created_at timestamptz not null default now()
);
alter table public.kimathy_allowed_users enable row level security;
revoke all on public.kimathy_allowed_users from public, anon, authenticated;

create or replace function public.kimathy_is_authorized_user()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.kimathy_allowed_users allowed
    where allowed.user_id = (select auth.uid())
  );
$$;
revoke all on function public.kimathy_is_authorized_user() from public, anon;
grant execute on function public.kimathy_is_authorized_user() to authenticated;

alter table public.daily_fixtures enable row level security;
alter table public.daily_accumulators enable row level security;
alter table public.daily_accumulator_legs enable row level security;

-- Remove any previous broad read policies before installing owner-only policies.
do $$
declare policy_row record;
begin
  for policy_row in
    select schemaname, tablename, policyname
    from pg_policies
    where schemaname = 'public'
      and tablename in ('daily_fixtures', 'daily_accumulators', 'daily_accumulator_legs')
  loop
    execute format('drop policy if exists %I on public.%I', policy_row.policyname, policy_row.tablename);
  end loop;
end $$;

revoke all on public.daily_fixtures, public.daily_accumulators, public.daily_accumulator_legs from public, anon, authenticated;
grant select on public.daily_fixtures, public.daily_accumulators, public.daily_accumulator_legs to authenticated;

create policy "allowlisted user can read daily fixtures"
  on public.daily_fixtures for select to authenticated
  using ((select public.kimathy_is_authorized_user()));
create policy "allowlisted user can read daily accumulators"
  on public.daily_accumulators for select to authenticated
  using ((select public.kimathy_is_authorized_user()));
create policy "allowlisted user can read accumulator legs"
  on public.daily_accumulator_legs for select to authenticated
  using ((select public.kimathy_is_authorized_user()));

comment on table public.daily_fixtures is 'Eligible, evidence-backed market candidates and verified settlement statuses.';
comment on column public.daily_fixtures.confidence_score is '0–100 heuristic ranking score; not a calibrated event probability.';
comment on table public.daily_accumulators is 'One immutable daily accumulator snapshot and verified result summary.';
comment on column public.daily_accumulators.net_units is 'Paper-tracking result at a fixed one-unit stake; not actual user profit.';
comment on table public.daily_accumulator_legs is 'Ordered accumulator legs with the odds and ranking score captured at build time.';
