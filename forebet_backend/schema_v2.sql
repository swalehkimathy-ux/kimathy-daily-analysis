-- K96 PICKS · schema_v2.sql (PHASE 3 migration — idempotent, safe to re-run)
-- Run kwenye Supabase → SQL Editor → New query → paste → RUN
-- ────────────────────────────────────────────────────────────────────────────

-- 1. picks: analytics columns (Phase 3–5)
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

-- 2. tunza history ya picks: kamwe USIFUTE day_cache zenye picks (spec D4)
--    NB: migration BETTER — badala ya fk change tumia trigger block (rahisi & safe)
create or replace function public.block_day_cache_delete() returns trigger
language plpgsql as $$
begin
  if exists (select 1 from public.picks where day = old.day limit 1)
     or exists (select 1 from public.matches where day = old.day limit 1) then
    raise exception 'day_cache % ina data (picks/matches) — hufutwi (history!)', old.day;
  end if;
  return old;
end $$;
drop trigger if exists trg_block_daycache_delete on public.day_cache;
create trigger trg_block_daycache_delete before delete on public.day_cache
  for each row execute function public.block_day_cache_delete();

-- 3. bookmaker odds snapshots (value + closing-line data) — spec 7.3/D6
create table if not exists public.odds_snapshots (
  id bigint generated always as identity primary key,
  day date not null, sport text not null, home text not null, away text not null,
  bookmaker text not null, market text not null, outcome text not null,
  line numeric(5,2), odds numeric(7,3) not null, suspended boolean default false,
  taken_at timestamptz not null default now()
);
create index if not exists idx_odds_snap_day on public.odds_snapshots(day);

-- 4. slips (Phase 5 mbele; tunawaandalia table sasa)
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

-- 5. RLS: hakuna anon read/write; worker service_role pekee
alter table public.odds_snapshots enable row level security;
alter table public.slips          enable row level security;
alter table public.slip_legs      enable row level security;
drop policy if exists anon_read_slips on public.slips;
drop policy if exists anon_read_slip_legs on public.slip_legs;
-- Tables zote za betting/private data: hakuna anon policy; service_role worker pekee.

-- 6. calibration view (Phase 6 mbele)
create or replace view public.calibration as
select width_bucket(p_cal, 0, 1, 20) as bucket, count(*) as n,
       round(avg(p_cal)::numeric, 3) as avg_pred,
       round((count(*) filter (where result='win'))::numeric
             / nullif(count(*) filter (where result in ('win','loss')),0), 3) as actual
from public.picks where result in ('win','loss') and p_cal is not null
group by 1 order by 1;
