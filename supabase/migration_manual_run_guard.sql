-- Kimathy: secure manual-only trigger with an atomic once-per-calendar-day limit (Africa/Dar_es_Salaam).
-- Run or re-run safely in Supabase SQL Editor after migration_private_dashboard.sql.
-- The browser can only read status or invoke the Edge Function; the service role
-- reserves/claims the daily request before any sports-provider API request.

create extension if not exists pgcrypto;

create table if not exists public.kimathy_manual_run_guard (
  guard_id smallint primary key default 1 check (guard_id = 1),
  last_requested_at timestamptz,
  last_started_at timestamptz,
  reserved_at timestamptz,
  reservation_id uuid,
  reservation_previous_requested_at timestamptz
);

-- Safe to re-run if the guard table was created by an earlier draft.
alter table public.kimathy_manual_run_guard
  add column if not exists last_requested_at timestamptz;
alter table public.kimathy_manual_run_guard
  add column if not exists last_started_at timestamptz;
alter table public.kimathy_manual_run_guard
  add column if not exists reserved_at timestamptz;
alter table public.kimathy_manual_run_guard
  add column if not exists reservation_id uuid;
alter table public.kimathy_manual_run_guard
  add column if not exists reservation_previous_requested_at timestamptz;

insert into public.kimathy_manual_run_guard (guard_id)
values (1)
on conflict (guard_id) do nothing;

alter table public.kimathy_manual_run_guard enable row level security;
revoke all on public.kimathy_manual_run_guard from public, anon, authenticated;
grant select, insert, update on public.kimathy_manual_run_guard to service_role;

create or replace function public.kimathy_reserve_manual_run()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_now timestamptz := clock_timestamp();
  v_last_requested timestamptz;
  v_reserved timestamptz;
  v_reservation uuid := gen_random_uuid();
begin
  insert into public.kimathy_manual_run_guard (guard_id)
  values (1)
  on conflict (guard_id) do nothing;

  select last_requested_at, reserved_at
    into v_last_requested, v_reserved
    from public.kimathy_manual_run_guard
   where guard_id = 1
   for update;

  if v_last_requested is not null
     and (v_last_requested at time zone 'Africa/Dar_es_Salaam')::date
         = (v_now at time zone 'Africa/Dar_es_Salaam')::date then
    return jsonb_build_object(
      'allowed', false,
      'reason', 'cooldown',
      'last_requested_at', v_last_requested,
      'next_allowed_at', (((v_last_requested at time zone 'Africa/Dar_es_Salaam')::date + 1)::timestamp at time zone 'Africa/Dar_es_Salaam')
    );
  end if;

  if v_reserved is not null and v_now < v_reserved + interval '15 minutes' then
    return jsonb_build_object(
      'allowed', false,
      'reason', 'request_pending',
      'next_allowed_at', v_reserved + interval '15 minutes'
    );
  end if;

  update public.kimathy_manual_run_guard
     set reservation_previous_requested_at = last_requested_at,
         last_requested_at = v_now,
         reserved_at = v_now,
         reservation_id = v_reservation
   where guard_id = 1;

  return jsonb_build_object(
    'allowed', true,
    'reservation_id', v_reservation,
    'reserved_at', v_now,
    'reservation_expires_at', v_now + interval '15 minutes',
    'next_allowed_at', (((v_now at time zone 'Africa/Dar_es_Salaam')::date + 1)::timestamp at time zone 'Africa/Dar_es_Salaam')
  );
end;
$$;

create or replace function public.kimathy_release_manual_run(p_reservation_id uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_changed integer;
begin
  update public.kimathy_manual_run_guard
     set last_requested_at = reservation_previous_requested_at,
         reserved_at = null,
         reservation_id = null,
         reservation_previous_requested_at = null
   where guard_id = 1
     and reservation_id = p_reservation_id;
  get diagnostics v_changed = row_count;
  return v_changed = 1;
end;
$$;

-- Earlier local drafts briefly used a finalize RPC. It is unnecessary and is
-- removed because the workflow must see its short-lived reservation when it starts.
drop function if exists public.kimathy_finalize_manual_run(uuid);

create or replace function public.kimathy_claim_manual_run()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_now timestamptz := clock_timestamp();
  v_last_requested timestamptz;
  v_reserved timestamptz;
begin
  insert into public.kimathy_manual_run_guard (guard_id)
  values (1)
  on conflict (guard_id) do nothing;

  select last_requested_at, reserved_at
    into v_last_requested, v_reserved
    from public.kimathy_manual_run_guard
   where guard_id = 1
   for update;

  -- The app's short-lived reservation authorizes exactly one workflow to pass
  -- even though it has already recorded the calendar-day limit at request time.
  if v_reserved is not null and v_now < v_reserved + interval '15 minutes' then
    update public.kimathy_manual_run_guard
       set last_started_at = v_now,
           reserved_at = null,
           reservation_id = null,
           reservation_previous_requested_at = null
     where guard_id = 1;

    return jsonb_build_object(
      'allowed', true,
      'last_started_at', v_now,
      'next_allowed_at', (((v_last_requested at time zone 'Africa/Dar_es_Salaam')::date + 1)::timestamp at time zone 'Africa/Dar_es_Salaam')
    );
  end if;

  if v_reserved is not null then
    update public.kimathy_manual_run_guard
       set reserved_at = null,
           reservation_id = null,
           reservation_previous_requested_at = null
     where guard_id = 1;
  end if;

  if v_last_requested is not null
     and (v_last_requested at time zone 'Africa/Dar_es_Salaam')::date
         = (v_now at time zone 'Africa/Dar_es_Salaam')::date then
    return jsonb_build_object(
      'allowed', false,
      'reason', 'cooldown',
      'last_requested_at', v_last_requested,
      'next_allowed_at', (((v_last_requested at time zone 'Africa/Dar_es_Salaam')::date + 1)::timestamp at time zone 'Africa/Dar_es_Salaam')
    );
  end if;

  -- Also protect direct workflow_dispatch runs that did not come from the app.
  update public.kimathy_manual_run_guard
     set last_requested_at = v_now,
         last_started_at = v_now,
         reserved_at = null,
         reservation_id = null,
         reservation_previous_requested_at = null
   where guard_id = 1;

  return jsonb_build_object(
    'allowed', true,
    'last_started_at', v_now,
    'next_allowed_at', (((v_now at time zone 'Africa/Dar_es_Salaam')::date + 1)::timestamp at time zone 'Africa/Dar_es_Salaam')
  );
end;
$$;

create or replace function public.kimathy_manual_run_status()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_now timestamptz := clock_timestamp();
  v_last_requested timestamptz;
  v_reserved timestamptz;
begin
  if not public.kimathy_is_authorized_user() then
    raise exception 'Not authorized';
  end if;

  select last_requested_at, reserved_at
    into v_last_requested, v_reserved
    from public.kimathy_manual_run_guard
   where guard_id = 1;

  if v_last_requested is not null
     and (v_last_requested at time zone 'Africa/Dar_es_Salaam')::date
         = (v_now at time zone 'Africa/Dar_es_Salaam')::date then
    return jsonb_build_object(
      'allowed', false,
      'reason', 'cooldown',
      'last_requested_at', v_last_requested,
      'next_allowed_at', (((v_last_requested at time zone 'Africa/Dar_es_Salaam')::date + 1)::timestamp at time zone 'Africa/Dar_es_Salaam')
    );
  end if;

  if v_reserved is not null and v_now < v_reserved + interval '15 minutes' then
    return jsonb_build_object(
      'allowed', false,
      'reason', 'request_pending',
      'next_allowed_at', v_reserved + interval '15 minutes'
    );
  end if;

  return jsonb_build_object(
    'allowed', true,
    'last_requested_at', v_last_requested,
    'next_allowed_at', null
  );
end;
$$;

revoke all on function public.kimathy_reserve_manual_run() from public, anon, authenticated;
revoke all on function public.kimathy_release_manual_run(uuid) from public, anon, authenticated;
revoke all on function public.kimathy_claim_manual_run() from public, anon, authenticated;
revoke all on function public.kimathy_manual_run_status() from public, anon;
grant execute on function public.kimathy_reserve_manual_run() to service_role;
grant execute on function public.kimathy_release_manual_run(uuid) to service_role;
grant execute on function public.kimathy_claim_manual_run() to service_role;
grant execute on function public.kimathy_manual_run_status() to authenticated;

comment on table public.kimathy_manual_run_guard is 'Atomic guard for at most one manual sports-analysis trigger per Africa/Dar_es_Salaam calendar day.';
