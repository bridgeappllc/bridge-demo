-- Delete smoke-test users (display names starting with "Smoke") and everything they created.
-- Deleting the auth user cascades to profiles, bridges they own, memberships, answers, ratings, messages.
delete from auth.users u
where u.id not in ('174fa4f3-a1f5-4a78-bd8b-00cb53cc8682','b4e7fa32-1470-458e-bbb7-d131e233de06')  -- real users, never delete
  and (u.id in (select id from public.profiles where display_name like 'Smoke%')
   or u.id in (select user_id from public.bridge_members where display_name like 'Smoke%'));
