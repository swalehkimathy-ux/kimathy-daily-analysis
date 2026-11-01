-- K96 PICKS — schema_v3_security.sql (v2.8.2)
-- Inaondoa maonyo ya Supabase Security Advisor (picha: "Security Definer View" + "Function Search Path Mutable").
-- Salama: haibadilishi data yoyote. Endesha MARA MOJA: Supabase -> SQL Editor -> New query -> paste -> RUN.

-- 1) Views ziendeshwe kwa ruhusa za anayeuliza (si za mmiliki) — "Security Definer View" (CRITICAL)
alter view public.engine_stats set (security_invoker = on);
alter view public.calibration  set (security_invoker = on);

-- 2) Function ya kulinda history iwe na search_path iliyofungwa — "Function Search Path Mutable"
alter function public.block_day_cache_delete() set search_path = public;

-- Ukaguzi: lazima zirudishe mistari (worker inatumia service_role, haiathiriki)
select 'engine_stats' as view, count(*) from public.engine_stats
union all
select 'calibration', count(*) from public.calibration;
