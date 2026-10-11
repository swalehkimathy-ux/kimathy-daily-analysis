-- Safe upgrade for an existing Kimathy Supabase project.
-- Run once in Supabase Dashboard → SQL Editor after downloading the updated app.
-- This migration fails closed for browser access until an owner is allowlisted.

create extension if not exists pgcrypto;

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

alter table public.daily_accumulators add column if not exists settlement_status text not null default 'pending';
alter table public.daily_accumulators add column if not exists settled_at timestamptz;
alter table public.daily_accumulators add column if not exists settled_total_odds numeric(8,4);
alter table public.daily_accumulators add column if not exists net_units numeric(10,4);
do $$
declare constraint_row record;
begin
  for constraint_row in
    select conname from pg_constraint
    where conrelid = 'public.daily_accumulators'::regclass
      and contype = 'c'
      and pg_get_constraintdef(oid) ilike '%settlement_status%'
  loop
    execute format('alter table public.daily_accumulators drop constraint %I', constraint_row.conname);
  end loop;
  update public.daily_accumulators
  set settlement_status = 'not_applicable'
  where status = 'no_ticket' and settlement_status = 'pending';
  alter table public.daily_accumulators
    add constraint daily_accumulators_settlement_status_check
    check (settlement_status in ('pending', 'won', 'lost', 'void', 'not_applicable'));
end $$;

-- Ensure the historical-ticket child table exists even if an earlier schema
-- version did not create it yet.
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

create unique index if not exists uq_daily_fixtures_selection
  on public.daily_fixtures (sport_type, match_name, match_time, market_name);
create unique index if not exists uq_accumulator_legs_order
  on public.daily_accumulator_legs (accumulator_id, leg_order);
create unique index if not exists uq_accumulator_legs_fixture
  on public.daily_accumulator_legs (accumulator_id, fixture_id);

-- Normalize legacy result labels and replace any older status constraint.
do $$
declare constraint_row record;
begin
  for constraint_row in
    select conname from pg_constraint
    where conrelid = 'public.daily_fixtures'::regclass
      and contype = 'c'
      and pg_get_constraintdef(oid) ilike '%status%'
  loop
    execute format('alter table public.daily_fixtures drop constraint %I', constraint_row.conname);
  end loop;
  update public.daily_fixtures set status = 'win' where status = 'won';
  update public.daily_fixtures set status = 'loss' where status = 'lost';
  alter table public.daily_fixtures
    add constraint daily_fixtures_status_check
    check (status in ('pending', 'win', 'loss', 'void'));
end $$;

create index if not exists idx_fixtures_market_status_time
  on public.daily_fixtures (market_key, status, match_time);
create index if not exists idx_accumulator_history
  on public.daily_accumulators (analysis_date desc, status, settlement_status);
create index if not exists idx_accumulator_legs_fixture
  on public.daily_accumulator_legs (fixture_id);

-- Remove only clearly marked interface-test rows from the earlier dashboard build.
delete from public.daily_fixtures
where source = 'interface-test'
   or match_name ilike 'TEST ONLY%';

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

-- After you create your Supabase Auth user, authorize it by running the
-- separate `supabase/authorize-owner-template.sql` with your login email.
