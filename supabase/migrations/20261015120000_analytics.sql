-- First-party, privacy-friendly usage analytics (additive only).
-- No cookies, no ad IDs, no third parties: signed-in clients insert small event rows for THEMSELVES only,
-- nobody (no client) can read them; aggregate numbers come only from admin_stats(), restricted to stats_admins.

create table if not exists public.events (
  id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  name text not null check (name in ('app_open','pod_created','clip_shared','answer_submitted','message_sent','library_add','invite_joined')),
  props jsonb not null default '{}'::jsonb check (jsonb_typeof(props) = 'object' and pg_column_size(props) <= 512),
  created_at timestamptz not null default now()
);
create index if not exists events_created_idx on public.events (created_at);
create index if not exists events_user_idx on public.events (user_id, created_at);
alter table public.events enable row level security;
revoke all on public.events from anon, authenticated;
grant insert (name, props) on public.events to authenticated;
grant usage on sequence public.events_id_seq to authenticated;
drop policy if exists events_insert_own on public.events;
create policy events_insert_own on public.events for insert to authenticated with check (user_id = auth.uid());
-- (no select/update/delete policies: users can't read or change events)

-- Who may see aggregate stats (matched against the signed-in, non-anonymous auth email).
create table if not exists public.stats_admins (email text primary key check (email = lower(email)));
alter table public.stats_admins enable row level security;
revoke all on public.stats_admins from anon, authenticated;
insert into public.stats_admins(email) values ('paul@paraglidemaui.com'), ('gurrieripaul@gmail.com') on conflict do nothing;

create or replace function public.is_stats_admin() returns boolean
language sql stable security definer set search_path = public, auth as $$
  select exists (select 1 from auth.users u join public.stats_admins a on a.email = lower(u.email)
                 where u.id = auth.uid() and coalesce(u.is_anonymous, false) = false and u.email is not null)
$$;
revoke all on function public.is_stats_admin() from public, anon;
grant execute on function public.is_stats_admin() to authenticated;

create or replace function public.admin_stats() returns jsonb
language plpgsql stable security definer set search_path = public, auth as $$
declare r jsonb;
begin
  if not public.is_stats_admin() then raise exception 'not allowed' using errcode = '42501'; end if;
  with real_users as (   -- people with a profile, excluding test (Smoke*) accounts
    select p.id, p.created_at as signed_up from profiles p where p.display_name not ilike 'smoke%'
  ), act as (            -- any first-party event or content created = activity
    select user_id uid, created_at t from events
    union all select created_by, created_at from bridges
    union all select user_id, joined_at from bridge_members
    union all select user_id, created_at from answers
    union all select user_id, created_at from ratings
    union all select user_id, created_at from messages
    union all select user_id, created_at from library_items
    union all select owner, created_at from group_pods
    union all select shared_by, created_at from group_pod_clips
    union all select user_id, created_at from group_pod_answers
    union all select user_id, created_at from group_pod_messages
    union all select id, signed_up from real_users
  ), a as (select act.uid, act.t from act join real_users u on u.id = act.uid),
  ratings_all as (
    select score::numeric s, user_id from ratings where score is not null
    union all select rating, user_id from answers where rating is not null
    union all select rating, user_id from group_pod_answers where rating is not null
  ),
  ret as (
    select d, count(*) filter (where u.signed_up <= now() - make_interval(days => d)) cohort,
           count(*) filter (where u.signed_up <= now() - make_interval(days => d)
                            and exists (select 1 from a where a.uid = u.id and a.t >= u.signed_up + make_interval(days => d))) kept
    from real_users u cross join (values (7), (30)) v(d) group by d
  )
  select jsonb_build_object(
    'generated_at', now(),
    'dau', (select count(distinct uid) from a where t > now() - interval '1 day'),
    'wau', (select count(distinct uid) from a where t > now() - interval '7 days'),
    'mau', (select count(distinct uid) from a where t > now() - interval '30 days'),
    'total_signups', (select count(*) from real_users),
    'signups_per_week', (select coalesce(jsonb_agg(jsonb_build_object('week', w, 'n', n) order by w), '[]') from (
        select to_char(gs, 'YYYY-MM-DD') w, (select count(*) from real_users where signed_up >= gs and signed_up < gs + interval '7 days') n
        from generate_series(date_trunc('week', now()) - interval '7 weeks', date_trunc('week', now()), interval '1 week') gs) x),
    'pods_created', (select count(*) from bridges b join real_users u on u.id = b.created_by)
                  + (select count(*) from group_pods g join real_users u on u.id = g.owner),
    'clips_shared', (select count(*) from bridges b join real_users u on u.id = b.created_by)
                  + (select count(*) from group_pod_clips c join real_users u on u.id = c.shared_by),
    'answers', (select count(*) from answers x join real_users u on u.id = x.user_id)
             + (select count(*) from group_pod_answers x join real_users u on u.id = x.user_id),
    'messages', (select count(*) from messages x join real_users u on u.id = x.user_id)
              + (select count(*) from group_pod_messages x join real_users u on u.id = x.user_id),
    'library_items', (select count(*) from library_items x join real_users u on u.id = x.user_id),
    'invites_joined', (select count(*) from bridge_members m join real_users u on u.id = m.user_id where m.role <> 'owner'),
    'ratings', (select count(*) from ratings_all x join real_users u on u.id = x.user_id),
    'avg_rating', (select round(avg(s), 1) from ratings_all x join real_users u on u.id = x.user_id),
    'retention_7d', (select jsonb_build_object('cohort', cohort, 'retained', kept, 'pct', case when cohort > 0 then round(100.0 * kept / cohort) end) from ret where d = 7),
    'retention_30d', (select jsonb_build_object('cohort', cohort, 'retained', kept, 'pct', case when cohort > 0 then round(100.0 * kept / cohort) end) from ret where d = 30),
    'events_7d', (select coalesce(jsonb_object_agg(name, n), '{}') from (select e.name, count(*) n from events e join real_users u on u.id = e.user_id
                   where e.created_at > now() - interval '7 days' group by e.name) z)
  ) into r;
  return r;
end $$;
revoke all on function public.admin_stats() from public, anon;
grant execute on function public.admin_stats() to authenticated;
