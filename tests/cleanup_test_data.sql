-- Delete smoke-test users (display names starting with "Smoke") and everything they created.
-- Deleting the auth user cascades to profiles, bridges they own, memberships, answers, ratings, messages,
-- library items, friendships and blocks.
delete from auth.users u
where u.id not in ('174fa4f3-a1f5-4a78-bd8b-00cb53cc8682','b4e7fa32-1470-458e-bbb7-d131e233de06',  -- real users, never delete
                   'cac07ef2-cd5e-48f4-9a62-c194ce6c559e','bf577153-2444-4cd4-a1c3-4fc34274cb4b','17f0950d-8f74-4c9c-b5d5-e1f2df1f342f')
  and (u.id in (select id from public.profiles where display_name like 'Smoke%')
   or u.id in (select user_id from public.bridge_members where display_name like 'Smoke%'));
