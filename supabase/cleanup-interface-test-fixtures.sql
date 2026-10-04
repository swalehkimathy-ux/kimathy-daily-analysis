-- Delete only the temporary interface-test rows inserted by interface-test-fixtures.sql.
-- Safe to run after checking the dashboard; other fixture sources are untouched.
delete from public.daily_fixtures
where source = 'interface-test';
