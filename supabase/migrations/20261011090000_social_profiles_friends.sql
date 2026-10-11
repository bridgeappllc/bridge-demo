-- =====================================================================
-- Bridge social: public profiles (@username, bio), friends (requests),
-- blocks, and a per-user library visibility setting.
-- Additive / backward compatible with the live app:
--   * profiles gets 3 new columns with defaults (no existing value changes)
--   * new tables friendships, blocks; new functions
--   * the library read policy is replaced by one that allows everything the
--     old one did for the default setting ('friends': friends AND bridge
--     partners can see it), plus 'everyone' / 'private' when a user opts in.
-- Nothing is dropped except that one policy (replaced in the same transaction).
-- =====================================================================

-- ------------------------------------------------------------ profiles
alter table public.profiles
  add column username text,
  add column bio text not null default '',
  add column library_visibility text not null default 'friends';
alter table public.profiles
  add constraint profiles_username_format check (username is null or username ~ '^[a-z0-9_]{3,20}$'),
  add constraint profiles_bio_length check (char_length(bio) <= 160),
  add constraint profiles_library_visibility check (library_visibility in ('everyone', 'friends', 'private'));
create unique index profiles_username_key on public.profiles (username);
-- own row stays the only directly readable profile row; other people are read through the RPCs below
grant insert (username, bio, library_visibility) on public.profiles to authenticated;
grant update (username, bio, library_visibility) on public.profiles to authenticated;

-- ------------------------------------------------------------ friendships
create table public.friendships (
  requester    uuid not null references auth.users(id) on delete cascade,
  addressee    uuid not null references auth.users(id) on delete cascade,
  status       text not null default 'pending' check (status in ('pending', 'accepted')),
  created_at   timestamptz not null default now(),
  responded_at timestamptz,
  primary key (requester, addressee),
  check (requester <> addressee)
);
-- one row per pair, whichever direction it was sent in
create unique index friendships_pair_key on public.friendships (least(requester, addressee), greatest(requester, addressee));
create index friendships_addressee_idx on public.friendships (addressee);
alter table public.friendships enable row level security;
create policy "see own friendships" on public.friendships for select to authenticated
  using (requester = (select auth.uid()) or addressee = (select auth.uid()));
revoke all on public.friendships from anon, authenticated;
grant select on public.friendships to authenticated;          -- all writes go through the RPCs

-- ------------------------------------------------------------ blocks
create table public.blocks (
  blocker    uuid not null references auth.users(id) on delete cascade,
  blocked    uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (blocker, blocked),
  check (blocker <> blocked)
);
create index blocks_blocked_idx on public.blocks (blocked);
alter table public.blocks enable row level security;
create policy "see who I blocked" on public.blocks for select to authenticated using (blocker = (select auth.uid()));
revoke all on public.blocks from anon, authenticated;
grant select on public.blocks to authenticated;

-- ------------------------------------------------------------ helpers
create function private.are_friends(a uuid, b uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.friendships f where f.status = 'accepted'
    and ((f.requester = a and f.addressee = b) or (f.requester = b and f.addressee = a)));
$$;
create function private.is_blocked(a uuid, b uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.blocks k where (k.blocker = a and k.blocked = b) or (k.blocker = b and k.blocked = a));
$$;
-- relation of the caller to `other`: self | friends | outgoing | incoming | none
create function private.friend_status(other uuid) returns text
language sql stable security definer set search_path = '' as $$
  select case
    when other = auth.uid() then 'self'
    when exists (select 1 from public.friendships f where f.requester = auth.uid() and f.addressee = other and f.status = 'accepted')
      or exists (select 1 from public.friendships f where f.requester = other and f.addressee = auth.uid() and f.status = 'accepted') then 'friends'
    when exists (select 1 from public.friendships f where f.requester = auth.uid() and f.addressee = other) then 'outgoing'
    when exists (select 1 from public.friendships f where f.requester = other and f.addressee = auth.uid()) then 'incoming'
    else 'none' end;
$$;
-- Library visibility:  everyone = any signed-in user;  friends (default) = friends + bridge partners;
-- private = only the owner.  A block (either direction) always hides it.
create function private.can_view_library(owner uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select owner = auth.uid() or (
    auth.uid() is not null and not private.is_blocked(auth.uid(), owner) and
    coalesce((select case p.library_visibility
                       when 'everyone' then true
                       when 'friends'  then private.are_friends(auth.uid(), owner) or private.shares_bridge_with(owner)
                       else false end
              from public.profiles p where p.id = owner),
             private.shares_bridge_with(owner)));   -- no profile row: the old rule (bridge partners)
$$;

drop policy "read own library or a bridge partner's" on public.library_items;
create policy "read own library, or one its owner shares with me" on public.library_items for select to authenticated
  using (user_id = (select auth.uid()) or private.can_view_library(user_id));

-- ------------------------------------------------------------ read RPCs
-- Profile basics (name, @username, bio) are visible to signed-in users, except across a block.
create function private.search_people(p_q text)
returns table (id uuid, display_name text, username text, bio text, friend_status text)
language sql stable security definer set search_path = '' as $$
  with q as (select lower(btrim(regexp_replace(coalesce(p_q, ''), '^\s*@', ''))) as s),
       e as (select s, replace(replace(replace(s, '\', '\\'), '%', '\%'), '_', '\_') as l from q)
  select p.id, p.display_name, p.username, p.bio, private.friend_status(p.id)
  from public.profiles p, e
  where auth.uid() is not null and char_length(e.s) between 2 and 40 and p.id <> auth.uid()
    and not private.is_blocked(auth.uid(), p.id)
    and (p.username like e.l || '%' or lower(p.display_name) like '%' || e.l || '%')
  order by (p.username = e.s) desc, (lower(p.display_name) = e.s) desc, (lower(p.display_name) like e.l || '%') desc, p.display_name, p.id
  limit 20;
$$;

create function private.get_profile(p_id uuid, p_username text)
returns table (id uuid, display_name text, username text, bio text, created_at timestamptz, friend_status text,
               friends_count int, bridges_count int, library_count int, can_view_library boolean, library_visibility text)
language sql stable security definer set search_path = '' as $$
  select p.id, p.display_name, p.username, p.bio, p.created_at, private.friend_status(p.id),
    (select count(*)::int from public.friendships f where f.status = 'accepted' and (f.requester = p.id or f.addressee = p.id)),
    (select count(*)::int from public.bridge_members m where m.user_id = p.id),
    case when private.can_view_library(p.id) then (select count(*)::int from public.library_items l where l.user_id = p.id) end,
    private.can_view_library(p.id), p.library_visibility
  from public.profiles p
  where auth.uid() is not null
    and (p.id = p_id or (p_username is not null and p.username = lower(regexp_replace(btrim(p_username), '^@', ''))))
    and (p.id = auth.uid() or not private.is_blocked(auth.uid(), p.id))
  limit 1;
$$;

-- A user's friends: visible to the user and to their friends.
create function private.friends_of(p_user uuid)
returns table (id uuid, display_name text, username text, friend_status text)
language sql stable security definer set search_path = '' as $$
  select p.id, p.display_name, p.username, private.friend_status(p.id)
  from public.friendships f
  join public.profiles p on p.id = case when f.requester = p_user then f.addressee else f.requester end
  where f.status = 'accepted' and (f.requester = p_user or f.addressee = p_user)
    and auth.uid() is not null and (p_user = auth.uid() or private.are_friends(auth.uid(), p_user))
    and not private.is_blocked(auth.uid(), p.id)
  order by lower(p.display_name), p.id;
$$;

-- My pending requests (both directions)
create function private.my_requests()
returns table (id uuid, display_name text, username text, direction text, created_at timestamptz)
language sql stable security definer set search_path = '' as $$
  select p.id, p.display_name, p.username, case when f.requester = auth.uid() then 'outgoing' else 'incoming' end, f.created_at
  from public.friendships f
  join public.profiles p on p.id = case when f.requester = auth.uid() then f.addressee else f.requester end
  where f.status = 'pending' and auth.uid() in (f.requester, f.addressee)
  order by f.created_at desc;
$$;

-- People I've been in a bridge with who aren't my friends yet
create function private.suggest_people()
returns table (id uuid, display_name text, username text, bio text, friend_status text)
language sql stable security definer set search_path = '' as $$
  select x.id, x.display_name, x.username, x.bio, x.fs from (
    select distinct p.id, p.display_name, p.username, p.bio, private.friend_status(p.id) as fs
    from public.bridge_members a
    join public.bridge_members b on b.bridge_id = a.bridge_id and b.user_id <> a.user_id
    join public.profiles p on p.id = b.user_id
    where a.user_id = auth.uid() and not private.is_blocked(auth.uid(), p.id)) x
  where x.fs <> 'friends'
  order by lower(x.display_name), x.id limit 50;
$$;

create function private.my_blocks()
returns table (id uuid, display_name text, username text)
language sql stable security definer set search_path = '' as $$
  select p.id, p.display_name, p.username from public.blocks k join public.profiles p on p.id = k.blocked
  where k.blocker = auth.uid() order by k.created_at desc;
$$;

create function private.username_available(p_username text) returns boolean
language sql stable security definer set search_path = '' as $$
  select auth.uid() is not null and lower(btrim(p_username)) ~ '^[a-z0-9_]{3,20}$'
     and not exists (select 1 from public.profiles p where p.username = lower(btrim(p_username)) and p.id <> auth.uid());
$$;

-- ------------------------------------------------------------ write RPCs
create function private.send_friend_request(p_user uuid) returns text
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid();
begin
  if me is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  if p_user is null or p_user = me then raise exception 'You can''t add yourself' using errcode = '22023'; end if;
  if not exists (select 1 from public.profiles where id = me) then raise exception 'Create your profile first' using errcode = 'P0001'; end if;
  if not exists (select 1 from public.profiles where id = p_user) or private.is_blocked(me, p_user) then
    raise exception 'Person not found' using errcode = 'P0002'; end if;
  -- they already asked me -> accept
  update public.friendships set status = 'accepted', responded_at = now()
    where requester = p_user and addressee = me and status = 'pending';
  if found then return 'friends'; end if;
  if (select count(*) from public.friendships where requester = me and status = 'pending') >= 200 then
    raise exception 'Too many pending friend requests' using errcode = 'P0001'; end if;
  insert into public.friendships (requester, addressee) values (me, p_user) on conflict do nothing;
  return private.friend_status(p_user);
end $$;

create function private.respond_friend_request(p_user uuid, p_accept boolean) returns text
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid();
begin
  if me is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  if p_accept then
    update public.friendships set status = 'accepted', responded_at = now()
      where requester = p_user and addressee = me and status = 'pending';
  else
    delete from public.friendships where requester = p_user and addressee = me and status = 'pending';
  end if;
  return private.friend_status(p_user);
end $$;

-- cancel my request / decline theirs / unfriend
create function private.remove_friend(p_user uuid) returns text
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid();
begin
  if me is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  delete from public.friendships where (requester = me and addressee = p_user) or (requester = p_user and addressee = me);
  return 'none';
end $$;

create function private.block_user(p_user uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid();
begin
  if me is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  if p_user is null or p_user = me then raise exception 'Invalid person' using errcode = '22023'; end if;
  if not exists (select 1 from auth.users where id = p_user) then raise exception 'Person not found' using errcode = 'P0002'; end if;
  insert into public.blocks (blocker, blocked) values (me, p_user) on conflict do nothing;
  delete from public.friendships where (requester = me and addressee = p_user) or (requester = p_user and addressee = me);
end $$;

create function private.unblock_user(p_user uuid) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if auth.uid() is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  delete from public.blocks where blocker = auth.uid() and blocked = p_user;
end $$;

-- Start a bridge "directly" with a friend: the bridge owner adds an accepted friend as the 2nd member.
create function private.add_friend_to_bridge(p_bridge uuid, p_friend uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); n int; nm text;
begin
  if me is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  perform 1 from public.bridges where id = p_bridge and created_by = me for update;   -- lock, like join_bridge
  if not found then raise exception 'Bridge not found' using errcode = 'P0002'; end if;
  if exists (select 1 from public.bridge_members where bridge_id = p_bridge and user_id = p_friend) then return; end if;
  if not private.are_friends(me, p_friend) or private.is_blocked(me, p_friend) then
    raise exception 'You can only add friends to a bridge' using errcode = '42501'; end if;
  select count(*) into n from public.bridge_members where bridge_id = p_bridge;
  if n >= 2 then raise exception 'This bridge already has two people' using errcode = 'P0001'; end if;
  select display_name into nm from public.profiles where id = p_friend;
  insert into public.bridge_members (bridge_id, user_id, display_name, role) values (p_bridge, p_friend, nm, 'friend');
end $$;

-- ------------------------------------------------------------ public wrappers (SECURITY INVOKER)
create function public.search_people(p_q text) returns table (id uuid, display_name text, username text, bio text, friend_status text)
language sql stable security invoker set search_path = '' as $$ select * from private.search_people(p_q); $$;
create function public.get_profile(p_id uuid default null, p_username text default null)
returns table (id uuid, display_name text, username text, bio text, created_at timestamptz, friend_status text,
               friends_count int, bridges_count int, library_count int, can_view_library boolean, library_visibility text)
language sql stable security invoker set search_path = '' as $$ select * from private.get_profile(p_id, p_username); $$;
create function public.friends_of(p_user uuid) returns table (id uuid, display_name text, username text, friend_status text)
language sql stable security invoker set search_path = '' as $$ select * from private.friends_of(p_user); $$;
create function public.my_requests() returns table (id uuid, display_name text, username text, direction text, created_at timestamptz)
language sql stable security invoker set search_path = '' as $$ select * from private.my_requests(); $$;
create function public.suggest_people() returns table (id uuid, display_name text, username text, bio text, friend_status text)
language sql stable security invoker set search_path = '' as $$ select * from private.suggest_people(); $$;
create function public.my_blocks() returns table (id uuid, display_name text, username text)
language sql stable security invoker set search_path = '' as $$ select * from private.my_blocks(); $$;
create function public.username_available(p_username text) returns boolean
language sql stable security invoker set search_path = '' as $$ select private.username_available(p_username); $$;
create function public.send_friend_request(p_user uuid) returns text
language sql security invoker set search_path = '' as $$ select private.send_friend_request(p_user); $$;
create function public.respond_friend_request(p_user uuid, p_accept boolean) returns text
language sql security invoker set search_path = '' as $$ select private.respond_friend_request(p_user, p_accept); $$;
create function public.remove_friend(p_user uuid) returns text
language sql security invoker set search_path = '' as $$ select private.remove_friend(p_user); $$;
create function public.block_user(p_user uuid) returns void
language sql security invoker set search_path = '' as $$ select private.block_user(p_user); $$;
create function public.unblock_user(p_user uuid) returns void
language sql security invoker set search_path = '' as $$ select private.unblock_user(p_user); $$;
create function public.add_friend_to_bridge(p_bridge uuid, p_friend uuid) returns void
language sql security invoker set search_path = '' as $$ select private.add_friend_to_bridge(p_bridge, p_friend); $$;

do $$
declare f text;
begin
  foreach f in array array[
    'private.are_friends(uuid,uuid)', 'private.is_blocked(uuid,uuid)', 'private.friend_status(uuid)', 'private.can_view_library(uuid)',
    'private.search_people(text)', 'private.get_profile(uuid,text)', 'private.friends_of(uuid)', 'private.my_requests()',
    'private.suggest_people()', 'private.my_blocks()', 'private.username_available(text)', 'private.send_friend_request(uuid)',
    'private.respond_friend_request(uuid,boolean)', 'private.remove_friend(uuid)', 'private.block_user(uuid)', 'private.unblock_user(uuid)',
    'private.add_friend_to_bridge(uuid,uuid)',
    'public.search_people(text)', 'public.get_profile(uuid,text)', 'public.friends_of(uuid)', 'public.my_requests()',
    'public.suggest_people()', 'public.my_blocks()', 'public.username_available(text)', 'public.send_friend_request(uuid)',
    'public.respond_friend_request(uuid,boolean)', 'public.remove_friend(uuid)', 'public.block_user(uuid)', 'public.unblock_user(uuid)',
    'public.add_friend_to_bridge(uuid,uuid)']
  loop
    execute format('revoke execute on function %s from public, anon, authenticated', f);
    execute format('grant execute on function %s to authenticated', f);
  end loop;
end $$;
