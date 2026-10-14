-- Request-time anchored analysis-run ledger and full fixture-board persistence.
-- Apply once in the Supabase SQL editor before deploying the updated runner.

create table if not exists public.analysis_runs (
  id uuid primary key default gen_random_uuid(),
  analysis_date date not null,
  requested_at timestamptz not null,
  completed_at timestamptz,
  status text not null default 'completed' check (status in ('running', 'completed', 'failed')),
  source_scope text not null,
  fixture_count integer not null default 0 check (fixture_count >= 0),
  quote_fixture_count integer not null default 0 check (quote_fixture_count >= 0),
  market_option_count integer not null default 0 check (market_option_count >= 0),
  eligible_fixture_count integer not null default 0 check (eligible_fixture_count >= 0),
  coverage jsonb not null default '{}'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_analysis_runs_requested_at
  on public.analysis_runs (requested_at desc);
create index if not exists idx_analysis_runs_date
  on public.analysis_runs (analysis_date, requested_at desc);

create table if not exists public.analysis_fixtures (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.analysis_runs(id) on delete cascade,
  analysis_date date not null,
  sport_type text not null check (sport_type in ('football', 'basketball')),
  provider_fixture_id text not null,
  provider_home_team_id text,
  provider_away_team_id text,
  provider_league_id text,
  provider_season text,
  match_name text not null,
  home_team text not null,
  away_team text not null,
  match_time timestamptz not null,
  kickoff_time_known boolean not null default true,
  kickoff_time_source text not null default 'api-sports',
  competition text,
  country text,
  round text,
  provider_status text,
  fixture_state text not null default 'scheduled',
  analysis_status text not null,
  market_options jsonb not null default '[]'::jsonb,
  recommended_market jsonb,
  recommended_score numeric(5,2),
  selected_for_ticket boolean not null default false,
  analysis_note text,
  statistics_summary jsonb not null default '{}'::jsonb,
  forebet_url text,
  forebet_injuries_url text,
  statarea_url text,
  source text not null default 'api-sports-schedule',
  created_at timestamptz not null default now(),
  unique (run_id, sport_type, provider_fixture_id)
);
alter table public.analysis_fixtures add column if not exists kickoff_time_source text not null default 'api-sports';
create index if not exists idx_analysis_fixtures_run_time
  on public.analysis_fixtures (run_id, match_time);
create index if not exists idx_analysis_fixtures_date_sport
  on public.analysis_fixtures (analysis_date, sport_type, match_time);

alter table public.analysis_runs enable row level security;
alter table public.analysis_fixtures enable row level security;
revoke all on public.analysis_runs, public.analysis_fixtures from public, anon, authenticated;
grant select on public.analysis_runs, public.analysis_fixtures to authenticated;
grant select, insert, update, delete on public.analysis_runs, public.analysis_fixtures to service_role;

drop policy if exists "allowlisted user can read analysis runs" on public.analysis_runs;
drop policy if exists "allowlisted user can read analysis fixtures" on public.analysis_fixtures;
create policy "allowlisted user can read analysis runs"
  on public.analysis_runs for select to authenticated
  using ((select public.kimathy_is_authorized_user()));
create policy "allowlisted user can read analysis fixtures"
  on public.analysis_fixtures for select to authenticated
  using ((select public.kimathy_is_authorized_user()));

comment on table public.analysis_runs is 'Request-time anchored daily analysis run ledger with provider coverage, warnings, and counts.';
comment on table public.analysis_fixtures is 'Full same-day API-Sports schedule, including fixtures without Odds API quotes or sufficient statistics evidence.';
comment on column public.analysis_fixtures.recommended_score is '0–100 heuristic evidence ranking for the recommended market; not a calibrated event probability.';
