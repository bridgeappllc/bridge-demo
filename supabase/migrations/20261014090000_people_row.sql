-- People row (additive): newest signed-up people, keyset-paginated. Read-only, SECURITY DEFINER in private,
-- invoker wrapper in public. Excludes: yourself, blocked either way, unnamed guests, Smoke* test accounts.
-- Deleted accounts are gone already (profiles cascade on auth.users delete).
create index if not exists profiles_created_idx on public.profiles(created_at desc, id desc);

create or replace function private.list_people(p_before timestamptz default null, p_before_id uuid default null, p_limit int default 30)
returns table (id uuid, display_name text, username text, created_at timestamptz)
language sql stable security definer set search_path = '' as $$
  select p.id, p.display_name, p.username, p.created_at
  from public.profiles p join auth.users u on u.id = p.id
  where auth.uid() is not null and p.id <> auth.uid()
    and u.deleted_at is null
    and btrim(p.display_name) <> '' and lower(btrim(p.display_name)) not in ('guest', 'anonymous')
    and p.display_name not ilike 'smoke%'
    and not private.is_blocked(auth.uid(), p.id)
    and (p_before is null or (p.created_at, p.id) < (p_before, coalesce(p_before_id, 'ffffffff-ffff-ffff-ffff-ffffffffffff'::uuid)))
  order by p.created_at desc, p.id desc
  limit greatest(1, least(coalesce(p_limit, 30), 50));
$$;
create or replace function public.list_people(p_before timestamptz default null, p_before_id uuid default null, p_limit int default 30)
returns table (id uuid, display_name text, username text, created_at timestamptz)
language sql stable security invoker set search_path = '' as $$ select * from private.list_people(p_before, p_before_id, p_limit) $$;

revoke all on function private.list_people(timestamptz, uuid, int) from public, anon;
grant execute on function private.list_people(timestamptz, uuid, int) to authenticated;
revoke all on function public.list_people(timestamptz, uuid, int) from public, anon;
grant execute on function public.list_people(timestamptz, uuid, int) to authenticated;
