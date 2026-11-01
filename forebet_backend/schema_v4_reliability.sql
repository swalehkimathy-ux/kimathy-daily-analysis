-- K96 PICKS — schema_v4_reliability.sql
-- Run AFTER schema.sql, schema_v2.sql and schema_v3_security.sql.
-- Adds scrape verification metadata, immutable engine-run history, and private DB reads.

-- 1) Scrape lifecycle. Existing cache rows are retained and backfilled.
alter table public.day_cache
  add column if not exists scrape_status text,
  add column if not exists scrape_started_at timestamptz,
  add column if not exists scrape_completed_at timestamptz,
  add column if not exists scrape_error text;

-- Legacy cache counts were not verified against stored rows; force one fresh/verified scrape.
update public.day_cache
set scrape_status = 'unknown'
where scrape_status is null;

alter table public.day_cache alter column scrape_status set default 'pending';
do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'day_cache_scrape_status_check'
                 and conrelid = 'public.day_cache'::regclass) then
    alter table public.day_cache add constraint day_cache_scrape_status_check
      check (scrape_status in ('pending','running','succeeded','partial','failed','empty','unknown'));
  end if;
end $$;

-- 2) Each engine run is stored separately. A failed run never replaces the last good run.
create table if not exists public.analysis_runs (
  id bigint generated always as identity primary key,
  day date not null,
  status text not null default 'running'
    check (status in ('running','succeeded','failed')),
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  match_count integer not null default 0,
  picks_count integer not null default 0,
  slips_count integer not null default 0,
  is_demo boolean not null default false,
  error text
);
alter table public.analysis_runs add column if not exists is_demo boolean not null default false;
create index if not exists idx_analysis_runs_day_status_started
  on public.analysis_runs(day, status, started_at desc);

alter table public.picks
  add column if not exists run_id bigint references public.analysis_runs(id) on delete cascade;
alter table public.slips
  add column if not exists run_id bigint references public.analysis_runs(id) on delete cascade;

-- The old per-day unique key prevented keeping more than one run's picks.
do $$ declare c record; begin
  for c in
    select conname from pg_constraint
    where conrelid = 'public.picks'::regclass and contype = 'u'
      and pg_get_constraintdef(oid) = 'UNIQUE (day, home, away, market, tip)'
  loop
    execute format('alter table public.picks drop constraint %I', c.conname);
  end loop;
end $$;
create unique index if not exists idx_picks_run_match_market_tip
  on public.picks(run_id, home, away, market, tip) where run_id is not null;
create index if not exists idx_picks_day_run_result on public.picks(day, run_id, result);
create index if not exists idx_slips_day_run_result on public.slips(day, run_id, result);

-- 3) Do not expose private picks, slips, fixtures, or run metadata through the anon key.
-- The desktop GUI/worker uses the service-role key server-side and continues to work.
alter table public.analysis_runs enable row level security;
drop policy if exists anon_read_day_cache on public.day_cache;
drop policy if exists anon_read_matches on public.matches;
drop policy if exists anon_read_picks on public.picks;
drop policy if exists anon_read_slips on public.slips;
drop policy if exists anon_read_slip_legs on public.slip_legs;
-- No anon/authenticated SELECT policy is intentionally created.

-- 4) Ignore failed/incomplete runs in analytics. Legacy rows (run_id IS NULL) remain included.
create or replace view public.engine_stats as
select market, sport,
       count(*) as total,
       count(*) filter (where result = 'win') as wins,
       count(*) filter (where result = 'loss') as losses,
       round(100.0 * count(*) filter (where result = 'win')
         / nullif(count(*) filter (where result in ('win','loss')), 0), 1) as hit_pct,
       round(avg(conf)::numeric, 1) as avg_conf
from public.picks p
where (p.run_id is null and coalesce(p.league, '') not ilike 'K96 TEST%') or exists (
  select 1 from public.analysis_runs r
  where r.id = p.run_id and r.status = 'succeeded' and not r.is_demo
    and r.id = (select r2.id from public.analysis_runs r2
                where r2.day = r.day and r2.status = 'succeeded' and not r2.is_demo
                order by r2.started_at desc, r2.id desc limit 1)
)
group by market, sport
order by total desc;

create or replace view public.calibration as
select width_bucket(p.p_cal, 0, 1, 20) as bucket,
       count(*) as n,
       round(avg(p.p_cal)::numeric, 3) as avg_pred,
       round((count(*) filter (where p.result='win'))::numeric
         / nullif(count(*) filter (where p.result in ('win','loss')), 0), 3) as actual
from public.picks p
where p.result in ('win','loss') and p.p_cal is not null
  and ((p.run_id is null and coalesce(p.league, '') not ilike 'K96 TEST%') or exists (
    select 1 from public.analysis_runs r
    where r.id = p.run_id and r.status = 'succeeded' and not r.is_demo
      and r.id = (select r2.id from public.analysis_runs r2
                  where r2.day = r.day and r2.status = 'succeeded' and not r2.is_demo
                  order by r2.started_at desc, r2.id desc limit 1)
  ))
group by 1 order by 1;

alter view public.engine_stats set (security_invoker = on);
alter view public.calibration set (security_invoker = on);

create or replace view public.calibration_samples as
select p.p_cal, p.result
from public.picks p
where p.result in ('win','loss') and p.p_cal is not null
  and ((p.run_id is null and coalesce(p.league, '') not ilike 'K96 TEST%') or exists (
    select 1 from public.analysis_runs r
    where r.id = p.run_id and r.status = 'succeeded' and not r.is_demo
      and r.id = (select r2.id from public.analysis_runs r2
                  where r2.day = r.day and r2.status = 'succeeded' and not r2.is_demo
                  order by r2.started_at desc, r2.id desc limit 1)
  ));
alter view public.calibration_samples set (security_invoker = on);

-- 5) Re-scrapes often omit enrichment/final fields. Preserve known values when a refresh sends NULL.
create or replace function public.preserve_match_known_values() returns trigger
language plpgsql set search_path = public as $$
begin
  if new.final_home is null then new.final_home := old.final_home; end if;
  if new.final_away is null then new.final_away := old.final_away; end if;
  if new.h2h is null then new.h2h := old.h2h; end if;
  if new.avg_h is null then new.avg_h := old.avg_h; end if;
  if new.avg_a is null then new.avg_a := old.avg_a; end if;
  if new.form_home is null then new.form_home := old.form_home; end if;
  if new.form_away is null then new.form_away := old.form_away; end if;
  if new.home_pos is null then new.home_pos := old.home_pos; end if;
  if new.away_pos is null then new.away_pos := old.away_pos; end if;
  return new;
end $$;
drop trigger if exists trg_preserve_match_known_values on public.matches;
create trigger trg_preserve_match_known_values before update on public.matches
for each row execute function public.preserve_match_known_values();
