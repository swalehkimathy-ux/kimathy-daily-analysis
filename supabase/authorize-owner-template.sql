-- One-time owner authorization for the private Kimathy dashboard.
-- 1) Create the owner under Supabase Dashboard → Authentication → Users (Add user).
-- 2) Replace the email below with that exact login email, then run this SQL.
-- 3) The email is used only by this SQL query; it is not written into app files.

insert into public.kimathy_allowed_users (user_id)
select id
from auth.users
where lower(email) = lower('REPLACE_WITH_YOUR_SUPABASE_LOGIN_EMAIL')
on conflict (user_id) do nothing;

-- Check that exactly one user was authorized:
select count(*) as authorized_owner_count
from public.kimathy_allowed_users;
