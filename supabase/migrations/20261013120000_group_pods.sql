-- Group pods: a named pod of up to 12 people with shared clips (3 questions each) and one group chat.
-- ADDITIVE ONLY: new tables / functions / triggers, one new nullable column on notifications and a wider list of
-- notification kinds. 2-person pods (bridges, invite links, direct sends) are untouched, and an app that doesn't
-- know about group pods keeps working.
--
-- Design (answer-then-talk, kept simple):
--   * A pod has members, a list of shared clips and ONE group chat.
--   * Every member answers the 3 questions for each clip; you see the others' answers to a clip once you've answered it.
--   * The group chat (read + write) is open once you've answered the pod's NEWEST clip (or when nothing is shared yet),
--     so a new clip re-locks the chat until you've listened and answered.
--   * All writes go through SECURITY DEFINER RPCs (rate-limited, blocks respected); tables are read-only via RLS.

-- ------------------------------------------------------------ tables
create table if not exists public.group_pods (
  id          uuid primary key default gen_random_uuid(),
  name        text not null check (char_length(btrim(name)) between 1 and 60),
  owner       uuid references auth.users(id) on delete set null,
  max_members int  not null default 12 check (max_members between 2 and 12),
  created_at  timestamptz not null default now()
);
create index if not exists group_pods_owner_idx on public.group_pods(owner);

create table if not exists public.group_pod_members (
  pod_id       uuid not null references public.group_pods(id) on delete cascade,
  user_id      uuid not null references auth.users(id) on delete cascade,
  display_name text not null check (char_length(btrim(display_name)) between 1 and 40),
  role         text not null default 'member' check (role in ('owner','member')),
  added_by     uuid references auth.users(id) on delete set null,
  joined_at    timestamptz not null default now(),
  primary key (pod_id, user_id)
);
create index if not exists group_pod_members_user_idx on public.group_pod_members(user_id);
create index if not exists group_pod_members_added_by_idx on public.group_pod_members(added_by);

create table if not exists public.group_pod_clips (
  id             uuid primary key default gen_random_uuid(),
  pod_id         uuid not null references public.group_pods(id) on delete cascade,
  shared_by      uuid references auth.users(id) on delete set null,
  shared_by_name text not null default '' check (char_length(shared_by_name) <= 40),
  title          text not null check (char_length(btrim(title)) between 1 and 300),
  url            text not null check (url ~* '^https?://' and char_length(url) <= 2000),
  kind           text not null default 'Article' check (char_length(kind) <= 20),
  note           text not null default '' check (char_length(note) <= 300),
  created_at     timestamptz not null default now()
);
create index if not exists group_pod_clips_pod_idx on public.group_pod_clips(pod_id, created_at desc);
create index if not exists group_pod_clips_shared_by_idx on public.group_pod_clips(shared_by);

create table if not exists public.group_pod_answers (
  clip_id    uuid not null references public.group_pod_clips(id) on delete cascade,
  user_id    uuid not null references auth.users(id) on delete cascade,
  a1 text not null check (char_length(btrim(a1)) between 1 and 4000),
  a2 text not null check (char_length(btrim(a2)) between 1 and 4000),
  a3 text not null check (char_length(btrim(a3)) between 1 and 4000),
  created_at timestamptz not null default now(),
  primary key (clip_id, user_id)
);
create index if not exists group_pod_answers_user_idx on public.group_pod_answers(user_id);

create table if not exists public.group_pod_messages (
  id           bigint generated always as identity primary key,
  pod_id       uuid not null references public.group_pods(id) on delete cascade,
  user_id      uuid not null references auth.users(id) on delete cascade,
  display_name text not null default '' check (char_length(display_name) <= 40),
  body         text not null check (char_length(btrim(body)) between 1 and 2000),
  created_at   timestamptz not null default now()
);
create index if not exists group_pod_messages_pod_idx on public.group_pod_messages(pod_id, id);
create index if not exists group_pod_messages_user_idx on public.group_pod_messages(user_id, created_at desc);

-- ------------------------------------------------------------ helpers (security definer: used inside policies)
create or replace function private.is_group_member(p_pod uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.group_pod_members where pod_id = p_pod and user_id = auth.uid());
$$;
create or replace function private.group_clip_answered(p_clip uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.group_pod_answers where clip_id = p_clip and user_id = auth.uid());
$$;
-- chat open = nothing shared yet, or I've answered the newest clip
create or replace function private.group_chat_open(p_pod uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select coalesce((select exists (select 1 from public.group_pod_answers a where a.clip_id = c.id and a.user_id = auth.uid())
                     from public.group_pod_clips c where c.pod_id = p_pod order by c.created_at desc, c.id desc limit 1), true);
$$;
create or replace function private.group_pod_of_clip(p_clip uuid) returns uuid
language sql stable security definer set search_path = '' as $$ select pod_id from public.group_pod_clips where id = p_clip; $$;

-- ------------------------------------------------------------ RLS (read-only for members; writes only via RPCs)
alter table public.group_pods         enable row level security;
alter table public.group_pod_members  enable row level security;
alter table public.group_pod_clips    enable row level security;
alter table public.group_pod_answers  enable row level security;
alter table public.group_pod_messages enable row level security;
revoke all on public.group_pods, public.group_pod_members, public.group_pod_clips, public.group_pod_answers, public.group_pod_messages from anon, authenticated;
grant select on public.group_pods, public.group_pod_members, public.group_pod_clips, public.group_pod_answers, public.group_pod_messages to authenticated;

drop policy if exists "members read group pod" on public.group_pods;
create policy "members read group pod" on public.group_pods for select to authenticated using (private.is_group_member(id));
drop policy if exists "members read group members" on public.group_pod_members;
create policy "members read group members" on public.group_pod_members for select to authenticated using (private.is_group_member(pod_id));
drop policy if exists "members read group clips" on public.group_pod_clips;
create policy "members read group clips" on public.group_pod_clips for select to authenticated
  using (private.is_group_member(pod_id) and (shared_by is null or shared_by = (select auth.uid()) or not private.is_blocked((select auth.uid()), shared_by)));
drop policy if exists "own answers, others after answering" on public.group_pod_answers;
create policy "own answers, others after answering" on public.group_pod_answers for select to authenticated
  using (user_id = (select auth.uid())
         or (private.is_group_member(private.group_pod_of_clip(clip_id)) and private.group_clip_answered(clip_id)
             and not private.is_blocked((select auth.uid()), user_id)));
drop policy if exists "members read group chat once open" on public.group_pod_messages;
create policy "members read group chat once open" on public.group_pod_messages for select to authenticated
  using (private.is_group_member(pod_id) and private.group_chat_open(pod_id)
         and (user_id = (select auth.uid()) or not private.is_blocked((select auth.uid()), user_id)));

-- ------------------------------------------------------------ word filter (same rules as names / chat / answers)
create or replace function private.tg_mod_group() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_table_name = 'group_pods' then
    perform private.mod_reject(new.name, 'name', true);
  elsif tg_table_name = 'group_pod_clips' then
    perform private.mod_reject(new.title, 'title', false); new.title := private.mod_mask(new.title);
    perform private.mod_reject(new.note, 'note', false);   new.note := private.mod_mask(new.note);
  elsif tg_table_name = 'group_pod_answers' then
    perform private.mod_reject(new.a1, 'a1', false); new.a1 := private.mod_mask(new.a1);
    perform private.mod_reject(new.a2, 'a2', false); new.a2 := private.mod_mask(new.a2);
    perform private.mod_reject(new.a3, 'a3', false); new.a3 := private.mod_mask(new.a3);
  elsif tg_table_name = 'group_pod_messages' then
    perform private.mod_reject(new.body, 'body', false); new.body := private.mod_mask(new.body);
  end if;
  return new;
end $$;
drop trigger if exists group_pods_content_filter on public.group_pods;
create trigger group_pods_content_filter before insert or update of name on public.group_pods for each row execute function private.tg_mod_group();
drop trigger if exists group_pod_clips_content_filter on public.group_pod_clips;
create trigger group_pod_clips_content_filter before insert on public.group_pod_clips for each row execute function private.tg_mod_group();
drop trigger if exists group_pod_answers_content_filter on public.group_pod_answers;
create trigger group_pod_answers_content_filter before insert on public.group_pod_answers for each row execute function private.tg_mod_group();
drop trigger if exists group_pod_messages_content_filter on public.group_pod_messages;
create trigger group_pod_messages_content_filter before insert on public.group_pod_messages for each row execute function private.tg_mod_group();

-- someone left / was removed / deleted their account: hand the pod to the longest-standing member, or drop an empty pod
create or replace function private.tg_group_member_gone() returns trigger
language plpgsql security definer set search_path = '' as $$
declare nxt uuid;
begin
  if not exists (select 1 from public.group_pods where id = old.pod_id) then return null; end if;  -- pod itself is being deleted
  if not exists (select 1 from public.group_pod_members where pod_id = old.pod_id) then
    delete from public.group_pods where id = old.pod_id; return null; end if;
  if not exists (select 1 from public.group_pod_members where pod_id = old.pod_id and role = 'owner') then
    select user_id into nxt from public.group_pod_members where pod_id = old.pod_id order by joined_at, user_id limit 1;
    update public.group_pod_members set role = 'owner' where pod_id = old.pod_id and user_id = nxt;
    update public.group_pods set owner = nxt where id = old.pod_id;
  end if;
  return null;
end $$;
drop trigger if exists group_pod_members_gone on public.group_pod_members;
create trigger group_pod_members_gone after delete on public.group_pod_members for each row execute function private.tg_group_member_gone();

-- ------------------------------------------------------------ notifications
alter table public.notifications add column if not exists group_pod_id uuid references public.group_pods(id) on delete cascade;
create index if not exists notifications_group_pod_idx on public.notifications(group_pod_id) where group_pod_id is not null;
alter table public.notifications drop constraint if exists notifications_kind_check;
alter table public.notifications add constraint notifications_kind_check check (kind in
  ('direct_bridge','friend_request','friend_accepted','message','answered','joined','pod_added','pod_clip','pod_message'));

create or replace function private.notify_group(p_user uuid, p_kind text, p_actor uuid, p_pod uuid, p_title text)
returns void language plpgsql security definer set search_path = '' as $$
declare nm text;
begin
  if p_user is null or p_user = p_actor then return; end if;
  if p_actor is not null and private.is_blocked(p_user, p_actor) then return; end if;
  select display_name into nm from public.profiles where id = p_actor;
  if p_kind = 'pod_message' then   -- one unread row per pod, bumped
    update public.notifications set count = count + 1, created_at = now(), actor = p_actor, actor_name = left(coalesce(nm,''),40)
      where user_id = p_user and kind = 'pod_message' and group_pod_id = p_pod and read_at is null;
    if found then return; end if;
  end if;
  insert into public.notifications (user_id, kind, actor, actor_name, group_pod_id, title)
  values (p_user, p_kind, p_actor, left(coalesce(nm,''),40), p_pod, left(coalesce(p_title,''),300));
end $$;

-- ------------------------------------------------------------ RPCs
create or replace function private.add_group_members_core(p_pod uuid, p_members uuid[], p_me uuid, p_pod_name text) returns int
language plpgsql security definer set search_path = '' as $$
declare u uuid; nm text; n int := 0; cap int; cur int;
begin
  select max_members into cap from public.group_pods where id = p_pod;
  for u in select distinct x from unnest(coalesce(p_members, '{}')) x where x is not null and x <> p_me loop
    if exists (select 1 from public.group_pod_members where pod_id = p_pod and user_id = u) then continue; end if;
    select display_name into nm from public.profiles where id = u;
    if nm is null or private.is_blocked(p_me, u) then raise exception 'Person not found' using errcode = 'P0002'; end if;
    select count(*) into cur from public.group_pod_members where pod_id = p_pod;
    if cur >= cap then raise exception 'A pod can have up to % people', cap using errcode = 'P0001'; end if;
    insert into public.group_pod_members (pod_id, user_id, display_name, role, added_by) values (p_pod, u, left(nm,40), 'member', p_me);
    perform private.notify_group(u, 'pod_added', p_me, p_pod, p_pod_name);
    n := n + 1;
  end loop;
  return n;
end $$;

create or replace function private.create_group_pod(p_name text, p_members uuid[]) returns uuid
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); my_name text; pid uuid; nm text := btrim(coalesce(p_name,''));
begin
  if me is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  select display_name into my_name from public.profiles where id = me;
  if my_name is null then raise exception 'Create your profile first' using errcode = 'P0001'; end if;
  if char_length(nm) < 1 or char_length(nm) > 60 then raise exception 'Please give your pod a name (up to 60 characters)' using errcode = '22023'; end if;
  if coalesce(cardinality(p_members),0) < 1 then raise exception 'Pick at least one person' using errcode = '22023'; end if;
  if cardinality(p_members) > 11 then raise exception 'A pod can have up to 12 people' using errcode = 'P0001'; end if;
  if (select count(*) from public.group_pods where owner = me and created_at > now() - interval '1 day') >= 10 then
    raise exception 'You''ve created a lot of pods today. Please try again tomorrow.' using errcode = 'P0001'; end if;
  insert into public.group_pods (name, owner) values (nm, me) returning id into pid;
  insert into public.group_pod_members (pod_id, user_id, display_name, role, added_by) values (pid, me, left(my_name,40), 'owner', me);
  perform private.add_group_members_core(pid, p_members, me, nm);
  return pid;
end $$;

create or replace function private.add_group_members(p_pod uuid, p_members uuid[]) returns int
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); g public.group_pods;
begin
  if me is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  select * into g from public.group_pods where id = p_pod for update;
  if g.id is null or not private.is_group_member(p_pod) then raise exception 'Pod not found' using errcode = 'P0002'; end if;
  if g.owner is distinct from me then raise exception 'Only the pod owner can add people' using errcode = '42501'; end if;
  if (select count(*) from public.group_pod_members where added_by = me and user_id <> me and joined_at > now() - interval '1 hour') >= 40 then
    raise exception 'You''ve added a lot of people this hour. Please try again later.' using errcode = 'P0001'; end if;
  return private.add_group_members_core(p_pod, p_members, me, g.name);
end $$;

create or replace function private.remove_group_member(p_pod uuid, p_user uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid();
begin
  if me is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  if not exists (select 1 from public.group_pods where id = p_pod and owner = me) then
    raise exception 'Only the pod owner can remove people' using errcode = '42501'; end if;
  if p_user = me then raise exception 'Use Leave pod to leave' using errcode = '22023'; end if;
  delete from public.group_pod_members where pod_id = p_pod and user_id = p_user;
end $$;

create or replace function private.leave_group_pod(p_pod uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid();
begin
  if me is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  delete from public.group_pod_members where pod_id = p_pod and user_id = me;
  if not found then raise exception 'Pod not found' using errcode = 'P0002'; end if;
  update public.notifications set read_at = now() where user_id = me and group_pod_id = p_pod and read_at is null;
end $$;

create or replace function private.share_to_group_pod(p_pod uuid, p_title text, p_url text, p_kind text default 'Article', p_note text default '')
returns uuid language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); nm text; cid uuid; t text; r record;
begin
  if me is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  if not private.is_group_member(p_pod) then raise exception 'Pod not found' using errcode = 'P0002'; end if;
  if (select count(*) from public.group_pod_clips where shared_by = me and created_at > now() - interval '1 hour') >= 20 then
    raise exception 'You''ve shared a lot of clips this hour. Please try again later.' using errcode = 'P0001'; end if;
  select display_name into nm from public.group_pod_members where pod_id = p_pod and user_id = me;
  insert into public.group_pod_clips (pod_id, shared_by, shared_by_name, title, url, kind, note)
  values (p_pod, me, left(coalesce(nm,''),40), btrim(coalesce(p_title,'')), btrim(coalesce(p_url,'')),
          coalesce(nullif(btrim(p_kind),''),'Article'), btrim(coalesce(p_note,'')))
  returning id, title into cid, t;
  for r in select user_id from public.group_pod_members where pod_id = p_pod and user_id <> me loop
    perform private.notify_group(r.user_id, 'pod_clip', me, p_pod, t);
  end loop;
  return cid;
end $$;

create or replace function private.answer_group_clip(p_clip uuid, p_a1 text, p_a2 text, p_a3 text) returns void
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid();
begin
  if me is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  if not private.is_group_member(private.group_pod_of_clip(p_clip)) then raise exception 'Clip not found' using errcode = 'P0002'; end if;
  if private.group_clip_answered(p_clip) then raise exception 'You already answered this clip' using errcode = 'P0001'; end if;
  insert into public.group_pod_answers (clip_id, user_id, a1, a2, a3) values (p_clip, me, btrim(p_a1), btrim(p_a2), btrim(p_a3));
end $$;

create or replace function private.send_group_message(p_pod uuid, p_body text) returns bigint
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); nm text; g text; mid bigint; r record;
begin
  if me is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  if not private.is_group_member(p_pod) then raise exception 'Pod not found' using errcode = 'P0002'; end if;
  if not private.group_chat_open(p_pod) then raise exception 'Answer the newest clip to join the chat' using errcode = '42501'; end if;
  if (select count(*) from public.group_pod_messages where user_id = me and created_at > now() - interval '1 minute') >= 20 then
    raise exception 'You''re sending messages very fast. Please wait a moment.' using errcode = 'P0001'; end if;
  select display_name into nm from public.group_pod_members where pod_id = p_pod and user_id = me;
  select name into g from public.group_pods where id = p_pod;
  insert into public.group_pod_messages (pod_id, user_id, display_name, body) values (p_pod, me, left(coalesce(nm,''),40), btrim(coalesce(p_body,'')))
  returning id into mid;
  for r in select user_id from public.group_pod_members where pod_id = p_pod and user_id <> me loop
    perform private.notify_group(r.user_id, 'pod_message', me, p_pod, g);
  end loop;
  return mid;
end $$;

-- public wrappers (SECURITY INVOKER), like the rest of the API
create or replace function public.create_group_pod(p_name text, p_members uuid[]) returns uuid
language sql security invoker set search_path = '' as $$ select private.create_group_pod(p_name, p_members); $$;
create or replace function public.add_group_members(p_pod uuid, p_members uuid[]) returns int
language sql security invoker set search_path = '' as $$ select private.add_group_members(p_pod, p_members); $$;
create or replace function public.remove_group_member(p_pod uuid, p_user uuid) returns void
language sql security invoker set search_path = '' as $$ select private.remove_group_member(p_pod, p_user); $$;
create or replace function public.leave_group_pod(p_pod uuid) returns void
language sql security invoker set search_path = '' as $$ select private.leave_group_pod(p_pod); $$;
create or replace function public.share_to_group_pod(p_pod uuid, p_title text, p_url text, p_kind text default 'Article', p_note text default '') returns uuid
language sql security invoker set search_path = '' as $$ select private.share_to_group_pod(p_pod, p_title, p_url, p_kind, p_note); $$;
create or replace function public.answer_group_clip(p_clip uuid, p_a1 text, p_a2 text, p_a3 text) returns void
language sql security invoker set search_path = '' as $$ select private.answer_group_clip(p_clip, p_a1, p_a2, p_a3); $$;
create or replace function public.send_group_message(p_pod uuid, p_body text) returns bigint
language sql security invoker set search_path = '' as $$ select private.send_group_message(p_pod, p_body); $$;

revoke execute on function private.is_group_member(uuid), private.group_clip_answered(uuid), private.group_chat_open(uuid),
  private.group_pod_of_clip(uuid), private.tg_mod_group(), private.tg_group_member_gone(),
  private.notify_group(uuid,text,uuid,uuid,text), private.add_group_members_core(uuid,uuid[],uuid,text),
  private.create_group_pod(text,uuid[]), private.add_group_members(uuid,uuid[]), private.remove_group_member(uuid,uuid),
  private.leave_group_pod(uuid), private.share_to_group_pod(uuid,text,text,text,text),
  private.answer_group_clip(uuid,text,text,text), private.send_group_message(uuid,text) from public, anon, authenticated;
-- policy helpers + RPC bodies are callable by signed-in users (the wrappers run as the caller)
grant execute on function private.is_group_member(uuid), private.group_clip_answered(uuid), private.group_chat_open(uuid),
  private.group_pod_of_clip(uuid),
  private.create_group_pod(text,uuid[]), private.add_group_members(uuid,uuid[]), private.remove_group_member(uuid,uuid),
  private.leave_group_pod(uuid), private.share_to_group_pod(uuid,text,text,text,text),
  private.answer_group_clip(uuid,text,text,text), private.send_group_message(uuid,text) to authenticated;
revoke execute on function public.create_group_pod(text,uuid[]), public.add_group_members(uuid,uuid[]), public.remove_group_member(uuid,uuid),
  public.leave_group_pod(uuid), public.share_to_group_pod(uuid,text,text,text,text),
  public.answer_group_clip(uuid,text,text,text), public.send_group_message(uuid,text) from public, anon;
grant execute on function public.create_group_pod(text,uuid[]), public.add_group_members(uuid,uuid[]), public.remove_group_member(uuid,uuid),
  public.leave_group_pod(uuid), public.share_to_group_pod(uuid,text,text,text,text),
  public.answer_group_clip(uuid,text,text,text), public.send_group_message(uuid,text) to authenticated;

-- realtime: group chat, clips, answers and members update live (Realtime applies the select policies above)
do $$ declare t text; begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    foreach t in array array['group_pod_messages','group_pod_clips','group_pod_answers','group_pod_members'] loop
      if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = t) then
        execute format('alter publication supabase_realtime add table public.%I', t);
      end if;
    end loop;
  end if;
end $$;
