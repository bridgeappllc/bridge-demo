-- Store requirements: in-app account deletion + reporting content/users.
-- Additive and non-destructive: new columns/table/functions/trigger; one FK changes from CASCADE to SET NULL so a
-- partner's shared bridge survives when the other person deletes their account. No existing rows are changed.

-- ------------------------------------------------------------------ shared bridges survive a deleted account
alter table public.bridges add column partner_left_at timestamptz;  -- set when the other member's account was deleted
alter table public.bridges alter column created_by drop not null;
alter table public.bridges drop constraint bridges_created_by_fkey;
alter table public.bridges add constraint bridges_created_by_fkey
  foreign key (created_by) references auth.users(id) on delete set null;

-- When a member row disappears (account deleted, by the user or an admin): if someone is still on the bridge,
-- mark it closed (nobody new can join via the old invite; the app shows "Deleted user"); if nobody is left, delete it.
create function private.tg_member_left() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if exists (select 1 from public.bridge_members m where m.bridge_id = old.bridge_id) then
    update public.bridges set partner_left_at = coalesce(partner_left_at, now()) where id = old.bridge_id;
  else
    delete from public.bridges where id = old.bridge_id;
  end if;
  return null;
end $$;
create trigger bridge_members_left after delete on public.bridge_members
  for each row execute function private.tg_member_left();

-- Closed bridges can't be joined or have a friend added; the invite preview shows them as full.
create or replace function private.join_bridge(p_token text, p_display_name text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid(); bid uuid; closed timestamptz; n int;
begin
  if uid is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  select id, partner_left_at into bid, closed from public.bridges where invite_token = p_token for update;
  if bid is null then raise exception 'Invite link not found' using errcode = 'P0002'; end if;
  if exists (select 1 from public.bridge_members where bridge_id = bid and user_id = uid) then return bid; end if;
  select count(*) into n from public.bridge_members where bridge_id = bid;
  if n >= 2 or closed is not null then raise exception 'This bridge already has two people' using errcode = 'P0001'; end if;
  insert into public.bridge_members (bridge_id, user_id, display_name, role) values (bid, uid, btrim(p_display_name), 'friend');
  return bid;
end $$;

create or replace function private.preview_bridge(p_token text)
returns table (owner_name text, clip_title text, clip_url text, clip_type text, member_count int, is_member boolean, bridge_id uuid)
language sql stable security definer set search_path = '' as $$
  select coalesce((select m.display_name from public.bridge_members m where m.bridge_id = b.id and m.role = 'owner'), 'Deleted user'),
         b.clip_title, b.clip_url, b.clip_type,
         case when b.partner_left_at is not null then 2
              else (select count(*)::int from public.bridge_members m where m.bridge_id = b.id) end,
         exists (select 1 from public.bridge_members m where m.bridge_id = b.id and m.user_id = auth.uid()),
         case when exists (select 1 from public.bridge_members m where m.bridge_id = b.id and m.user_id = auth.uid()) then b.id end
  from public.bridges b where b.invite_token = p_token;
$$;

create or replace function private.add_friend_to_bridge(p_bridge uuid, p_friend uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); n int; nm text;
begin
  if me is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  perform 1 from public.bridges where id = p_bridge and created_by = me and partner_left_at is null for update;
  if not found then raise exception 'Bridge not found' using errcode = 'P0002'; end if;
  if exists (select 1 from public.bridge_members where bridge_id = p_bridge and user_id = p_friend) then return; end if;
  if not private.are_friends(me, p_friend) or private.is_blocked(me, p_friend) then
    raise exception 'You can only add friends to a bridge' using errcode = '42501'; end if;
  select count(*) into n from public.bridge_members where bridge_id = p_bridge;
  if n >= 2 then raise exception 'This bridge already has two people' using errcode = 'P0001'; end if;
  select display_name into nm from public.profiles where id = p_friend;
  insert into public.bridge_members (bridge_id, user_id, display_name, role) values (p_bridge, p_friend, nm, 'friend');
end $$;

-- ------------------------------------------------------------------ delete my account
-- Deletes the caller's auth user. Cascades remove their profile, library, friendships/requests, blocks, bridge
-- memberships and with them their answers, ratings and chat messages. Bridges only they were on are deleted;
-- shared bridges stay for the partner, closed and shown as "Deleted user" (trigger above). Reports they filed are
-- kept for moderation with the reporter removed; reports about them keep a text snapshot.
create function private.delete_my_account() returns void
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid();
begin
  if uid is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  delete from auth.users where id = uid;
end $$;
create function public.delete_my_account() returns void
language sql security invoker set search_path = '' as $$ select private.delete_my_account(); $$;

-- ------------------------------------------------------------------ reports
create table public.reports (
  id          bigint generated always as identity primary key,
  reporter    uuid references auth.users(id) on delete set null,
  target_type text not null check (target_type in ('user', 'library_item', 'message')),
  target_id   text not null check (char_length(target_id) between 1 and 64),
  target_user uuid references auth.users(id) on delete set null,
  reason      text not null check (reason in ('spam', 'harassment', 'hate', 'sexual', 'violence', 'self_harm', 'illegal', 'impersonation', 'other')),
  note        text not null default '' check (char_length(note) <= 1000),
  snapshot    text not null default '' check (char_length(snapshot) <= 4000),  -- what was reported, kept even if deleted later
  status      text not null default 'open' check (status in ('open', 'reviewed', 'actioned', 'dismissed')),
  created_at  timestamptz not null default now(),
  reviewed_at timestamptz,
  admin_note  text not null default ''
);
create index reports_status_idx on public.reports(status, created_at desc);
create index reports_reporter_idx on public.reports(reporter);
create index reports_target_user_idx on public.reports(target_user);
-- RLS on with no policies + no grants: app users can neither read nor write this table directly.
-- Reports are filed only through report_content(); only the project owner (SQL editor / dashboard) can read them.
alter table public.reports enable row level security;
revoke all on public.reports from public, anon, authenticated;

create function private.report_content(p_type text, p_id text, p_reason text, p_note text default '')
returns bigint
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); tu uuid; snap text; rid bigint;
begin
  if me is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  if (select count(*) from public.reports where reporter = me and created_at > now() - interval '1 day') >= 30 then
    raise exception 'Too many reports today. Please email bridgeappllc@gmail.com.' using errcode = 'P0001'; end if;
  if p_type = 'user' then
    select p.id, left(p.display_name || coalesce(' @' || p.username, '') || coalesce(' — ' || nullif(p.bio, ''), ''), 4000)
      into tu, snap from public.profiles p where p.id::text = p_id;
  elsif p_type = 'library_item' then
    select l.user_id, left(l.title || ' — ' || l.url || coalesce(' — note: ' || nullif(l.note, ''), ''), 4000)
      into tu, snap from public.library_items l
     where l.id::text = p_id and (l.user_id = me or private.can_view_library(l.user_id)
                                  or exists (select 1 from public.bridge_members a join public.bridge_members b using (bridge_id)
                                              where a.user_id = me and b.user_id = l.user_id));
  elsif p_type = 'message' then
    if p_id !~ '^[0-9]{1,18}$' then raise exception 'Not found' using errcode = 'P0002'; end if;
    select m.user_id, left(m.body, 4000) into tu, snap from public.messages m
     where m.id = p_id::bigint and private.is_bridge_member(m.bridge_id);
  else
    raise exception 'Unknown report type' using errcode = '22023';
  end if;
  if tu is null then raise exception 'Not found' using errcode = 'P0002'; end if;
  if tu = me then raise exception 'You can''t report yourself' using errcode = 'P0001'; end if;
  insert into public.reports (reporter, target_type, target_id, target_user, reason, note, snapshot)
  values (me, p_type, p_id, tu, p_reason, left(btrim(coalesce(p_note, '')), 1000), coalesce(snap, ''))
  returning id into rid;
  return rid;
end $$;
create function public.report_content(p_type text, p_id text, p_reason text, p_note text default '')
returns bigint language sql security invoker set search_path = '' as $$
  select private.report_content(p_type, p_id, p_reason, p_note);
$$;

-- Moderation queue for Paul (SQL editor only; the private schema is not exposed through the API):
--   select * from private.reports_review where status = 'open';
--   update public.reports set status = 'actioned', reviewed_at = now(), admin_note = '...' where id = 123;
create view private.reports_review with (security_invoker = true) as
  select r.id, r.created_at, r.status, r.target_type, r.reason, r.note, r.snapshot,
         r.target_user, tp.display_name as target_name, tp.username as target_username,
         r.reporter, rp.display_name as reporter_name, r.target_id, r.reviewed_at, r.admin_note,
         (select count(*) from public.reports x where x.target_user = r.target_user) as reports_against_target
    from public.reports r
    left join public.profiles tp on tp.id = r.target_user
    left join public.profiles rp on rp.id = r.reporter
   order by (r.status = 'open') desc, r.created_at desc;
revoke all on private.reports_review from public, anon, authenticated;

do $$
declare f text;
begin
  foreach f in array array['private.delete_my_account()', 'public.delete_my_account()',
    'private.report_content(text,text,text,text)', 'public.report_content(text,text,text,text)']
  loop
    execute format('revoke execute on function %s from public, anon, authenticated', f);
    execute format('grant execute on function %s to authenticated', f);
  end loop;
  -- replaced functions keep their existing grants; the trigger function is never called directly
  execute 'revoke execute on function private.tg_member_left() from public, anon, authenticated';
end $$;
