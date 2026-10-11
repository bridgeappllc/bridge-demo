-- Reserved @usernames: nobody can claim these (case doesn't matter; usernames are lowercase already).
-- Additive: one immutable helper, one CHECK constraint (no existing username was reserved when applied),
-- and username_available() now also says "no" for reserved names.
create function private.is_reserved_username(u text) returns boolean
language sql immutable set search_path = '' as $$
  select lower(coalesce(u, '')) = any (array[
    'bridge', 'bridges', 'bridgeapp', 'bridgeappllc', 'thebridge', 'meetonthebridge', 'clipclub',
    'admin', 'administrator', 'root', 'system', 'support', 'help', 'helpdesk', 'official',
    'staff', 'team', 'moderator', 'mod', 'security', 'privacy', 'legal', 'abuse', 'contact', 'info',
    'hello', 'noreply', 'no_reply', 'api', 'www', 'app', 'settings', 'profile', 'people', 'null', 'undefined']);
$$;
revoke execute on function private.is_reserved_username(text) from public, anon;
grant execute on function private.is_reserved_username(text) to authenticated;

alter table public.profiles
  add constraint profiles_username_not_reserved check (username is null or not private.is_reserved_username(username));

create or replace function private.username_available(p_username text) returns boolean
language sql stable security definer set search_path = '' as $$
  select auth.uid() is not null and lower(btrim(p_username)) ~ '^[a-z0-9_]{3,20}$'
     and not private.is_reserved_username(lower(btrim(p_username)))
     and not exists (select 1 from public.profiles p where p.username = lower(btrim(p_username)) and p.id <> auth.uid());
$$;
