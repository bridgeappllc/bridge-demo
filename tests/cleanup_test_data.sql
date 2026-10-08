-- Delete smoke-test users (display names starting with "Smoke") and everything they created.
-- Deleting the auth user cascades to profiles, bridges they own, memberships, answers, ratings, messages.
delete from auth.users u
where u.id in (select id from public.profiles where display_name like 'Smoke%')
   or u.id in (select user_id from public.bridge_members where display_name like 'Smoke%');
