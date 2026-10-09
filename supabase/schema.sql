-- =====================================================================
-- Bridge v1 — Supabase schema, row-level security, and RPCs  (v1 ONLY)
-- ⚠️  DO NOT RUN THIS ON THE LIVE PROJECT. It drops and recreates the Bridge
-- objects (ALL DATA IS LOST). The live project is managed with the files in
-- supabase/migrations/ (v1 = 20261008000000_bridge_v1.sql, v2 library =
-- 20261008160000_library_and_community.sql, v3 no rating step =
-- 20261009090000_remove_rating_step.sql). Historical v1 snapshot (it still has the
-- old rating step); for a fresh project apply the migration files in order instead.
--
-- Security model
--  * Every visitor gets a Supabase *anonymous* user (role "authenticated").
--  * Only members of a bridge can see that bridge, its members, answers,
--    ratings and messages.
--  * Becoming a member requires the bridge's secret invite token
--    (join_bridge RPC). Max 2 people per bridge (owner + 1 friend).
--  * You see your friend's answers only after you submit yours, and their
--    rating only after you submit yours. Chat (read + write) opens after
--    you rate. Answers and ratings are final once submitted.
--  * SECURITY DEFINER code lives in schema "private" (not exposed by the API).
--  * Tables are not writable directly except: own answers, own rating,
--    own chat messages, own profile. Bridges/memberships are created only
--    via the create_bridge / join_bridge functions.
-- =====================================================================

drop function if exists public.create_bridge(text,text,text,text,text,text,text,text) cascade;
drop function if exists public.join_bridge(text,text) cascade;
drop function if exists public.preview_bridge(text) cascade;
drop table if exists public.messages cascade;
drop table if exists public.ratings cascade;
drop table if exists public.answers cascade;
drop table if exists public.bridge_members cascade;
drop table if exists public.bridges cascade;
drop table if exists public.profiles cascade;
drop schema if exists private cascade;

-- Private (NOT exposed via the Data API) schema for SECURITY DEFINER code.
create schema private;
revoke all on schema private from public;
grant usage on schema private to anon, authenticated;

-- ---------------------------------------------------------------- tables
create table public.profiles (
  id           uuid primary key default auth.uid() references auth.users(id) on delete cascade,
  display_name text not null check (char_length(btrim(display_name)) between 1 and 40),
  topics       text[] not null default '{}',
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create table public.bridges (
  id           uuid primary key default gen_random_uuid(),
  invite_token text not null unique default replace(gen_random_uuid()::text, '-', ''),
  created_by   uuid not null references auth.users(id) on delete cascade,
  clip_title   text not null check (char_length(clip_title) between 1 and 300),
  clip_url     text not null check (clip_url ~* '^https?://' and char_length(clip_url) <= 2000),
  clip_type    text not null default 'Article' check (char_length(clip_type) <= 20),
  clip_cat     text not null default '' check (char_length(clip_cat) <= 40),
  clip_creator text not null default '' check (char_length(clip_creator) <= 120),
  friend_label text not null default '' check (char_length(friend_label) <= 40), -- what the owner called the friend before they joined
  reward       text not null default '' check (char_length(reward) <= 10),       -- DEMO ONLY: no payments
  created_at   timestamptz not null default now()
);

create index bridges_created_by_idx on public.bridges(created_by);

create table public.bridge_members (
  bridge_id    uuid not null references public.bridges(id) on delete cascade,
  user_id      uuid not null references auth.users(id) on delete cascade,
  display_name text not null check (char_length(btrim(display_name)) between 1 and 40),
  role         text not null check (role in ('owner','friend')),
  joined_at    timestamptz not null default now(),
  answered_at  timestamptz,   -- set by trigger; lets the friend see progress without seeing content
  rated_at     timestamptz,
  primary key (bridge_id, user_id)
);
create index bridge_members_user_idx on public.bridge_members(user_id);

create table public.answers (
  bridge_id  uuid not null,
  user_id    uuid not null default auth.uid(),
  a1 text not null check (char_length(btrim(a1)) between 1 and 4000),
  a2 text not null check (char_length(btrim(a2)) between 1 and 4000),
  a3 text not null check (char_length(btrim(a3)) between 1 and 4000),
  created_at timestamptz not null default now(),
  primary key (bridge_id, user_id),
  foreign key (bridge_id, user_id) references public.bridge_members(bridge_id, user_id) on delete cascade
);

create table public.ratings (
  bridge_id  uuid not null,
  user_id    uuid not null default auth.uid(),
  score      smallint not null check (score between 0 and 10),
  created_at timestamptz not null default now(),
  primary key (bridge_id, user_id),
  foreign key (bridge_id, user_id) references public.bridge_members(bridge_id, user_id) on delete cascade
);

create table public.messages (
  id         bigint generated always as identity primary key,
  bridge_id  uuid not null,
  user_id    uuid not null default auth.uid(),
  body       text not null check (char_length(btrim(body)) between 1 and 2000),
  created_at timestamptz not null default now(),
  foreign key (bridge_id, user_id) references public.bridge_members(bridge_id, user_id) on delete cascade
);
create index messages_bridge_idx on public.messages(bridge_id, id);
create index messages_member_idx on public.messages(bridge_id, user_id);

-- ------------------------------------------------- helper functions (RLS)
-- SECURITY DEFINER so policies can look at membership without recursing into RLS.
create function private.is_bridge_member(b uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.bridge_members m where m.bridge_id = b and m.user_id = auth.uid());
$$;
create function private.has_answered(b uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.answers a where a.bridge_id = b and a.user_id = auth.uid());
$$;
create function private.has_rated(b uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.ratings r where r.bridge_id = b and r.user_id = auth.uid());
$$;

-- progress flags on bridge_members
create function private.tg_mark_answered() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  update public.bridge_members set answered_at = now() where bridge_id = new.bridge_id and user_id = new.user_id;
  return new;
end $$;
create function private.tg_mark_rated() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  update public.bridge_members set rated_at = now() where bridge_id = new.bridge_id and user_id = new.user_id;
  return new;
end $$;
create trigger answers_mark after insert on public.answers for each row execute function private.tg_mark_answered();
create trigger ratings_mark after insert on public.ratings for each row execute function private.tg_mark_rated();

-- ------------------------------------------------------------------- RLS
alter table public.profiles       enable row level security;
alter table public.bridges        enable row level security;
alter table public.bridge_members enable row level security;
alter table public.answers        enable row level security;
alter table public.ratings        enable row level security;
alter table public.messages       enable row level security;

create policy "own profile: read"   on public.profiles for select to authenticated using (id = (select auth.uid()));
create policy "own profile: insert" on public.profiles for insert to authenticated with check (id = (select auth.uid()));
create policy "own profile: update" on public.profiles for update to authenticated using (id = (select auth.uid())) with check (id = (select auth.uid()));

create policy "members read bridge"   on public.bridges for select to authenticated using (private.is_bridge_member(id));
create policy "owner deletes bridge"  on public.bridges for delete to authenticated using (created_by = (select auth.uid()));

create policy "members read members"  on public.bridge_members for select to authenticated using (private.is_bridge_member(bridge_id));

create policy "read own answers, or friend's after answering" on public.answers for select to authenticated
  using (user_id = (select auth.uid()) or (private.is_bridge_member(bridge_id) and private.has_answered(bridge_id)));
create policy "members submit own answers" on public.answers for insert to authenticated
  with check (user_id = (select auth.uid()) and private.is_bridge_member(bridge_id));

create policy "read own rating, or friend's after rating" on public.ratings for select to authenticated
  using (user_id = (select auth.uid()) or (private.is_bridge_member(bridge_id) and private.has_rated(bridge_id)));
create policy "members rate after answering" on public.ratings for insert to authenticated
  with check (user_id = (select auth.uid()) and private.is_bridge_member(bridge_id) and private.has_answered(bridge_id));

create policy "members read chat after rating" on public.messages for select to authenticated
  using (private.is_bridge_member(bridge_id) and private.has_rated(bridge_id));
create policy "members chat after rating" on public.messages for insert to authenticated
  with check (user_id = (select auth.uid()) and private.is_bridge_member(bridge_id) and private.has_rated(bridge_id));

-- ---------------------------------------------------------------- grants
-- Supabase grants everything to anon/authenticated by default; tighten it.
revoke all on public.profiles, public.bridges, public.bridge_members, public.answers, public.ratings, public.messages from anon, authenticated;
grant select on public.bridges, public.bridge_members, public.answers, public.ratings, public.messages to authenticated;
grant delete on public.bridges to authenticated;
grant select on public.profiles to authenticated;
grant insert (id, display_name, topics) on public.profiles to authenticated;
grant update (display_name, topics, updated_at) on public.profiles to authenticated;
grant insert (bridge_id, user_id, a1, a2, a3) on public.answers to authenticated;
grant insert (bridge_id, user_id, score) on public.ratings to authenticated;
grant insert (bridge_id, user_id, body) on public.messages to authenticated;

-- ------------------------------------------------------------------ RPCs
-- Create a bridge and add the caller as owner. Returns the new bridge row (incl. invite_token).
create function private.create_bridge(
  p_display_name text, p_clip_title text, p_clip_url text, p_clip_type text default 'Article',
  p_clip_cat text default '', p_clip_creator text default '', p_friend_label text default '', p_reward text default ''
) returns public.bridges
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid(); b public.bridges;
begin
  if uid is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  insert into public.bridges (created_by, clip_title, clip_url, clip_type, clip_cat, clip_creator, friend_label, reward)
  values (uid, btrim(p_clip_title), btrim(p_clip_url), coalesce(nullif(btrim(p_clip_type),''),'Article'),
          coalesce(btrim(p_clip_cat),''), coalesce(btrim(p_clip_creator),''), coalesce(btrim(p_friend_label),''),
          coalesce(btrim(p_reward),''))
  returning * into b;
  insert into public.bridge_members (bridge_id, user_id, display_name, role)
  values (b.id, uid, btrim(p_display_name), 'owner');
  return b;
end $$;

-- Join a bridge with its invite token. Idempotent for existing members. Returns bridge id.
create function private.join_bridge(p_token text, p_display_name text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid(); bid uuid; n int;
begin
  if uid is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  select id into bid from public.bridges where invite_token = p_token for update;  -- lock: serialises concurrent joins
  if bid is null then raise exception 'Invite link not found' using errcode = 'P0002'; end if;
  if exists (select 1 from public.bridge_members where bridge_id = bid and user_id = uid) then return bid; end if;
  select count(*) into n from public.bridge_members where bridge_id = bid;
  if n >= 2 then raise exception 'This bridge already has two people' using errcode = 'P0001'; end if;
  insert into public.bridge_members (bridge_id, user_id, display_name, role) values (bid, uid, btrim(p_display_name), 'friend');
  return bid;
end $$;

-- What the invite landing page shows before joining (token holders only; reveals no answers/chat).
create function private.preview_bridge(p_token text)
returns table (owner_name text, clip_title text, clip_url text, clip_type text, member_count int, is_member boolean, bridge_id uuid)
language sql stable security definer set search_path = '' as $$
  select (select m.display_name from public.bridge_members m where m.bridge_id = b.id and m.role = 'owner'),
         b.clip_title, b.clip_url, b.clip_type,
         (select count(*)::int from public.bridge_members m where m.bridge_id = b.id),
         exists (select 1 from public.bridge_members m where m.bridge_id = b.id and m.user_id = auth.uid()),
         case when exists (select 1 from public.bridge_members m where m.bridge_id = b.id and m.user_id = auth.uid()) then b.id end
  from public.bridges b where b.invite_token = p_token;
$$;

-- Public RPC endpoints: thin SECURITY INVOKER wrappers around the private implementations.
create function public.create_bridge(
  p_display_name text, p_clip_title text, p_clip_url text, p_clip_type text default 'Article',
  p_clip_cat text default '', p_clip_creator text default '', p_friend_label text default '', p_reward text default ''
) returns public.bridges language sql security invoker set search_path = '' as $$
  select * from private.create_bridge(p_display_name, p_clip_title, p_clip_url, p_clip_type, p_clip_cat, p_clip_creator, p_friend_label, p_reward);
$$;
create function public.join_bridge(p_token text, p_display_name text) returns uuid
language sql security invoker set search_path = '' as $$
  select private.join_bridge(p_token, p_display_name);
$$;
create function public.preview_bridge(p_token text)
returns table (owner_name text, clip_title text, clip_url text, clip_type text, member_count int, is_member boolean, bridge_id uuid)
language sql stable security invoker set search_path = '' as $$
  select * from private.preview_bridge(p_token);
$$;

revoke execute on all functions in schema private from public, anon, authenticated;
revoke execute on function public.create_bridge(text,text,text,text,text,text,text,text), public.join_bridge(text,text), public.preview_bridge(text)
  from public, anon, authenticated;
-- helpers are called from RLS policies, which run as the requesting user
grant execute on function private.is_bridge_member(uuid), private.has_answered(uuid), private.has_rated(uuid) to authenticated;
grant execute on function private.create_bridge(text,text,text,text,text,text,text,text), private.join_bridge(text,text) to authenticated;
grant execute on function public.create_bridge(text,text,text,text,text,text,text,text), public.join_bridge(text,text) to authenticated;
grant execute on function private.preview_bridge(text), public.preview_bridge(text) to anon, authenticated;

-- -------------------------------------------------------------- realtime
-- Live chat/progress updates (the app also polls every few seconds as a fallback).
do $$ begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    alter publication supabase_realtime add table public.messages, public.bridge_members, public.answers, public.ratings;
  end if;
end $$;
