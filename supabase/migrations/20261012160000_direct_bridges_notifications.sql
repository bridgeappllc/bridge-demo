-- Direct "Send a bridge" + in-app notifications.  ADDITIVE ONLY: new nullable columns, a new table, new functions
-- and triggers. Apps that don't know about it keep working (live app ignores the new columns/table).

-- ------------------------------------------------------------ direct bridges
alter table public.bridges
  add column if not exists direct_to        uuid references auth.users(id) on delete set null,
  add column if not exists direct_to_name   text check (direct_to_name is null or char_length(direct_to_name) <= 40),
  add column if not exists direct_note      text check (direct_note is null or char_length(direct_note) <= 300),
  add column if not exists direct_status    text check (direct_status in ('pending','accepted','declined')),
  add column if not exists direct_sent_at   timestamptz;
create index if not exists bridges_direct_to_idx on public.bridges(direct_to) where direct_to is not null;

-- ------------------------------------------------------------ notifications
create table if not exists public.notifications (
  id          bigint generated always as identity primary key,
  user_id     uuid not null references auth.users(id) on delete cascade,      -- recipient
  kind        text not null check (kind in ('direct_bridge','friend_request','friend_accepted','message','answered','joined')),
  actor       uuid references auth.users(id) on delete set null,
  actor_name  text not null default '' check (char_length(actor_name) <= 40),
  bridge_id   uuid references public.bridges(id) on delete cascade,
  title       text not null default '' check (char_length(title) <= 300),
  count       int  not null default 1,
  created_at  timestamptz not null default now(),
  read_at     timestamptz
);
create index if not exists notifications_user_idx on public.notifications(user_id, created_at desc);
create index if not exists notifications_unread_idx on public.notifications(user_id) where read_at is null;
alter table public.notifications enable row level security;
revoke all on public.notifications from anon, authenticated;
grant select on public.notifications to authenticated;
grant update (read_at) on public.notifications to authenticated;
drop policy if exists "recipient reads own notifications" on public.notifications;
create policy "recipient reads own notifications" on public.notifications for select to authenticated
  using (user_id = (select auth.uid()));
drop policy if exists "recipient marks own notifications read" on public.notifications;
create policy "recipient marks own notifications read" on public.notifications for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
-- no insert/delete policy: rows are only written by the SECURITY DEFINER functions below.

create or replace function private.notify(p_user uuid, p_kind text, p_actor uuid, p_bridge uuid, p_title text)
returns void language plpgsql security definer set search_path = '' as $$
declare nm text;
begin
  if p_user is null or p_user = p_actor then return; end if;
  if p_actor is not null and private.is_blocked(p_user, p_actor) then return; end if;
  select display_name into nm from public.profiles where id = p_actor;
  if nm is null and p_bridge is not null then
    select display_name into nm from public.bridge_members where bridge_id = p_bridge and user_id = p_actor; end if;
  -- chat: one unread row per bridge, bumped instead of spamming
  if p_kind = 'message' then
    update public.notifications set count = count + 1, created_at = now(), actor = p_actor, actor_name = coalesce(nm,'')
      where user_id = p_user and kind = 'message' and bridge_id = p_bridge and read_at is null;
    if found then return; end if;
  end if;
  insert into public.notifications (user_id, kind, actor, actor_name, bridge_id, title)
  values (p_user, p_kind, p_actor, left(coalesce(nm,''),40), p_bridge, left(coalesce(p_title,''),300));
end $$;

-- friend request / accepted
create or replace function private.tg_notify_friendships() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' and new.status = 'pending' then
    perform private.notify(new.addressee, 'friend_request', new.requester, null, '');
  elsif tg_op = 'UPDATE' and new.status = 'accepted' and old.status is distinct from 'accepted' then
    perform private.notify(new.requester, 'friend_accepted', new.addressee, null, '');
  end if;
  return null;
end $$;
drop trigger if exists friendships_notify on public.friendships;
create trigger friendships_notify after insert or update of status on public.friendships
  for each row execute function private.tg_notify_friendships();

-- new chat message -> the other member(s)
create or replace function private.tg_notify_messages() returns trigger
language plpgsql security definer set search_path = '' as $$
declare r record; t text;
begin
  select clip_title into t from public.bridges where id = new.bridge_id;
  for r in select user_id from public.bridge_members where bridge_id = new.bridge_id and user_id <> new.user_id loop
    perform private.notify(r.user_id, 'message', new.user_id, new.bridge_id, t);
  end loop;
  return null;
end $$;
drop trigger if exists messages_notify on public.messages;
create trigger messages_notify after insert on public.messages
  for each row execute function private.tg_notify_messages();

-- partner answered / someone joined my bridge
create or replace function private.tg_notify_members() returns trigger
language plpgsql security definer set search_path = '' as $$
declare r record; t text;
begin
  select clip_title into t from public.bridges where id = new.bridge_id;
  for r in select user_id from public.bridge_members where bridge_id = new.bridge_id and user_id <> new.user_id loop
    if tg_op = 'INSERT' then perform private.notify(r.user_id, 'joined', new.user_id, new.bridge_id, t);
    elsif new.answered_at is not null and old.answered_at is null then perform private.notify(r.user_id, 'answered', new.user_id, new.bridge_id, t);
    end if;
  end loop;
  return null;
end $$;
drop trigger if exists bridge_members_notify on public.bridge_members;
create trigger bridge_members_notify after insert or update of answered_at on public.bridge_members
  for each row execute function private.tg_notify_members();

-- ------------------------------------------------------------ RPCs
-- Send a bridge straight to someone (friend or not). Blocked either way -> "not found". Rate-limited.
create or replace function private.send_direct_bridge(p_to uuid, p_clip_title text, p_clip_url text, p_clip_type text default 'Article',
  p_clip_cat text default '', p_clip_creator text default '', p_note text default '') returns uuid
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); my_name text; to_name text; b public.bridges; note text := btrim(coalesce(p_note,''));
begin
  if me is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  if p_to is null or p_to = me then raise exception 'You can''t send a bridge to yourself' using errcode = '22023'; end if;
  select display_name into my_name from public.profiles where id = me;
  if my_name is null then raise exception 'Create your profile first' using errcode = 'P0001'; end if;
  select display_name into to_name from public.profiles where id = p_to;
  if to_name is null or private.is_blocked(me, p_to) then raise exception 'Person not found' using errcode = 'P0002'; end if;
  if (select count(*) from public.bridges where created_by = me and direct_to is not null and direct_sent_at > now() - interval '1 hour') >= 10 then
    raise exception 'You''ve sent a lot of bridges this hour. Please try again later.' using errcode = 'P0001'; end if;
  if (select count(*) from public.bridges where created_by = me and direct_to = p_to and direct_status = 'pending') >= 3 then
    raise exception '% already has 3 bridges waiting from you. Wait for them to answer one first.', to_name using errcode = 'P0001'; end if;
  if char_length(note) > 300 then raise exception 'Note is too long' using errcode = '22001'; end if;
  perform private.mod_reject(note, 'note', false);
  select * into b from private.create_bridge(my_name, p_clip_title, p_clip_url, p_clip_type, p_clip_cat, p_clip_creator, to_name, '');
  update public.bridges set direct_to = p_to, direct_to_name = left(to_name,40), direct_note = nullif(private.mod_mask(note),''),
    direct_status = 'pending', direct_sent_at = now() where id = b.id;
  perform private.notify(p_to, 'direct_bridge', me, b.id, b.clip_title);
  return b.id;
end $$;

-- Bridges sent straight to me that I haven't answered yet.
create or replace function private.my_incoming_bridges()
returns table (id uuid, sender uuid, sender_name text, clip_title text, clip_url text, clip_type text, note text, sent_at timestamptz)
language sql stable security definer set search_path = '' as $$
  select b.id, b.created_by, coalesce((select m.display_name from public.bridge_members m where m.bridge_id = b.id and m.role = 'owner'), 'Deleted user'),
         b.clip_title, b.clip_url, b.clip_type, coalesce(b.direct_note,''), b.direct_sent_at
  from public.bridges b
  where b.direct_to = auth.uid() and b.direct_status = 'pending' and b.partner_left_at is null
    and not private.is_blocked(auth.uid(), b.created_by)
  order by b.direct_sent_at desc;
$$;

create or replace function private.respond_direct_bridge(p_bridge uuid, p_accept boolean) returns uuid
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); b public.bridges; nm text; n int;
begin
  if me is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  select * into b from public.bridges where id = p_bridge and direct_to = me for update;
  if b.id is null then raise exception 'Bridge not found' using errcode = 'P0002'; end if;
  if exists (select 1 from public.bridge_members where bridge_id = b.id and user_id = me) then return b.id; end if;
  if b.direct_status <> 'pending' or b.partner_left_at is not null or private.is_blocked(me, b.created_by) then
    raise exception 'This bridge is no longer available' using errcode = 'P0001'; end if;
  if not p_accept then update public.bridges set direct_status = 'declined' where id = b.id; return null; end if;
  select count(*) into n from public.bridge_members where bridge_id = b.id;
  if n >= 2 then raise exception 'This bridge already has two people' using errcode = 'P0001'; end if;
  select display_name into nm from public.profiles where id = me;
  if nm is null then raise exception 'Create your profile first' using errcode = 'P0001'; end if;
  update public.bridges set direct_status = 'accepted' where id = b.id;
  insert into public.bridge_members (bridge_id, user_id, display_name, role) values (b.id, me, nm, 'friend');
  update public.notifications set read_at = now() where user_id = me and bridge_id = b.id and kind = 'direct_bridge' and read_at is null;
  return b.id;
end $$;

-- invite links keep working; if someone else joins by link, a pending direct send is no longer pending
create or replace function private.tg_direct_joined() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  update public.bridges set direct_status = case when direct_to = new.user_id then 'accepted' else 'declined' end
    where id = new.bridge_id and direct_status = 'pending' and new.role = 'friend';
  return null;
end $$;
drop trigger if exists bridge_members_direct on public.bridge_members;
create trigger bridge_members_direct after insert on public.bridge_members
  for each row execute function private.tg_direct_joined();

create or replace function private.mark_notifications_read(p_ids bigint[]) returns int
language sql security definer set search_path = '' as $$
  with u as (update public.notifications set read_at = now()
             where user_id = auth.uid() and read_at is null and (p_ids is null or id = any(p_ids)) returning 1)
  select count(*)::int from u;
$$;

-- public wrappers (SECURITY INVOKER), like the rest of the API
create or replace function public.send_direct_bridge(p_to uuid, p_clip_title text, p_clip_url text, p_clip_type text default 'Article',
  p_clip_cat text default '', p_clip_creator text default '', p_note text default '') returns uuid
language sql security invoker set search_path = '' as $$
  select private.send_direct_bridge(p_to, p_clip_title, p_clip_url, p_clip_type, p_clip_cat, p_clip_creator, p_note); $$;
create or replace function public.my_incoming_bridges()
returns table (id uuid, sender uuid, sender_name text, clip_title text, clip_url text, clip_type text, note text, sent_at timestamptz)
language sql stable security invoker set search_path = '' as $$ select * from private.my_incoming_bridges(); $$;
create or replace function public.respond_direct_bridge(p_bridge uuid, p_accept boolean) returns uuid
language sql security invoker set search_path = '' as $$ select private.respond_direct_bridge(p_bridge, p_accept); $$;
create or replace function public.mark_notifications_read(p_ids bigint[] default null) returns int
language sql security invoker set search_path = '' as $$ select private.mark_notifications_read(p_ids); $$;

revoke execute on function private.notify(uuid,text,uuid,uuid,text), private.tg_notify_friendships(), private.tg_notify_messages(),
  private.tg_notify_members(), private.tg_direct_joined(),
  private.send_direct_bridge(uuid,text,text,text,text,text,text), private.my_incoming_bridges(),
  private.respond_direct_bridge(uuid,boolean), private.mark_notifications_read(bigint[]) from public, anon, authenticated;
revoke execute on function public.send_direct_bridge(uuid,text,text,text,text,text,text), public.my_incoming_bridges(),
  public.respond_direct_bridge(uuid,boolean), public.mark_notifications_read(bigint[]) from public, anon;
grant execute on function private.send_direct_bridge(uuid,text,text,text,text,text,text), private.my_incoming_bridges(),
  private.respond_direct_bridge(uuid,boolean), private.mark_notifications_read(bigint[]) to authenticated;
grant execute on function public.send_direct_bridge(uuid,text,text,text,text,text,text), public.my_incoming_bridges(),
  public.respond_direct_bridge(uuid,boolean), public.mark_notifications_read(bigint[]) to authenticated;

-- realtime: the bell updates live (Realtime applies the select policy above)
do $$ begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime')
     and not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'notifications') then
    alter publication supabase_realtime add table public.notifications;
  end if;
end $$;
