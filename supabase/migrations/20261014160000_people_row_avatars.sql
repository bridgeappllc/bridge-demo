-- People row v2 (additive): same rules as list_people, plus the avatar path (public "avatars" bucket, as on profiles).
-- list_people is kept unchanged for any client still calling it.
create or replace function private.list_people_v2(p_before timestamptz default null, p_before_id uuid default null, p_limit int default 30)
returns table (id uuid, display_name text, username text, avatar_url text, created_at timestamptz)
language sql stable security definer set search_path = '' as $$
  select l.id, l.display_name, l.username, p.avatar_url, l.created_at
  from private.list_people(p_before, p_before_id, p_limit) l join public.profiles p on p.id = l.id
  order by l.created_at desc, l.id desc;
$$;
create or replace function public.list_people_v2(p_before timestamptz default null, p_before_id uuid default null, p_limit int default 30)
returns table (id uuid, display_name text, username text, avatar_url text, created_at timestamptz)
language sql stable security invoker set search_path = '' as $$ select * from private.list_people_v2(p_before, p_before_id, p_limit) $$;
revoke all on function private.list_people_v2(timestamptz, uuid, int) from public, anon;
grant execute on function private.list_people_v2(timestamptz, uuid, int) to authenticated;
revoke all on function public.list_people_v2(timestamptz, uuid, int) from public, anon;
grant execute on function public.list_people_v2(timestamptz, uuid, int) to authenticated;
