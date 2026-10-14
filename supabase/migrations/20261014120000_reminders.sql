-- Email reminders (additive, safe on live). The 'remind' Edge Function verifies the caller's JWT, then calls
-- private.remind_prepare / private.remind_finish with the service role. Recipient emails never reach the client.
alter table public.profiles add column if not exists email_reminders boolean not null default true;
grant update (email_reminders) on public.profiles to authenticated;

create table if not exists public.pod_reminders (
  id         bigint generated always as identity primary key,
  sender     uuid not null references auth.users(id) on delete cascade,
  target     uuid not null references auth.users(id) on delete cascade,
  pod_kind   text not null check (pod_kind in ('bridge', 'group')),
  pod_id     uuid not null,
  status     text not null default 'pending' check (status in ('pending', 'sent')),
  created_at timestamptz not null default now()
);
create index if not exists pod_reminders_target_idx on public.pod_reminders(target, pod_id, created_at desc);
create index if not exists pod_reminders_sender_idx on public.pod_reminders(sender, created_at desc);
alter table public.pod_reminders enable row level security;
drop policy if exists "senders read own reminders" on public.pod_reminders;
create policy "senders read own reminders" on public.pod_reminders for select to authenticated using (sender = (select auth.uid()));
revoke all on public.pod_reminders from anon, authenticated;
grant select on public.pod_reminders to authenticated;

alter table public.notifications drop constraint if exists notifications_kind_check;
alter table public.notifications add constraint notifications_kind_check check (kind in
  ('direct_bridge','friend_request','friend_accepted','message','answered','joined','pod_added','pod_clip','pod_message','reminder'));

-- Core eligibility check. Returns the clip title, or raises a friendly error.
create or replace function private.remind_check(p_sender uuid, p_kind text, p_pod uuid, p_target uuid) returns text
language plpgsql stable security definer set search_path = '' as $$
declare t text; ok boolean;
begin
  if p_sender is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  if p_target = p_sender then raise exception 'You can''t remind yourself' using errcode = 'P0001'; end if;
  if p_kind = 'bridge' then
    if not exists (select 1 from public.bridge_members where bridge_id = p_pod and user_id = p_sender) then raise exception 'Pod not found' using errcode = 'P0002'; end if;
    select b.clip_title, m.answered_at is null into t, ok from public.bridges b join public.bridge_members m on m.bridge_id = b.id and m.user_id = p_target where b.id = p_pod;
    if t is null then raise exception 'They''re not in this pod' using errcode = 'P0002'; end if;
    if not ok then raise exception 'They already answered' using errcode = 'P0001'; end if;
  elsif p_kind = 'group' then
    if not exists (select 1 from public.group_pod_members where pod_id = p_pod and user_id = p_sender) then raise exception 'Pod not found' using errcode = 'P0002'; end if;
    if not exists (select 1 from public.group_pod_members where pod_id = p_pod and user_id = p_target) then raise exception 'They''re not in this pod' using errcode = 'P0002'; end if;
    select c.title, not exists (select 1 from public.group_pod_answers a where a.clip_id = c.id and a.user_id = p_target) into t, ok
      from public.group_pod_clips c where c.pod_id = p_pod order by c.created_at desc, c.id limit 1;
    if t is null then raise exception 'Nothing shared yet' using errcode = 'P0001'; end if;
    if not ok then raise exception 'They already answered' using errcode = 'P0001'; end if;
  else raise exception 'Unknown pod' using errcode = '22023';
  end if;
  if private.is_blocked(p_sender, p_target) then raise exception 'They''re not in this pod' using errcode = 'P0002'; end if;
  if not exists (select 1 from auth.users u join public.profiles p on p.id = u.id
                 where u.id = p_target and u.email is not null and u.email_confirmed_at is not null
                   and not coalesce(u.is_anonymous, false) and u.deleted_at is null and p.email_reminders) then
    raise exception 'They can''t get email reminders' using errcode = 'P0001'; end if;
  if exists (select 1 from public.pod_reminders where target = p_target and pod_id = p_pod and created_at > now() - interval '24 hours') then
    raise exception 'Already reminded in the last 24 hours' using errcode = 'P0001'; end if;
  if (select count(*) from public.pod_reminders where sender = p_sender and created_at > now() - interval '24 hours') >= 10 then
    raise exception 'You''ve sent 10 reminders today — try again tomorrow' using errcode = 'P0001'; end if;
  return t;
end $$;

-- For the client: which members I could remind right now (ids only, no emails).
create or replace function private.remindable(p_kind text, p_pod uuid) returns setof uuid
language plpgsql stable security definer set search_path = '' as $$
declare me uuid := auth.uid(); r record;
begin
  if me is null then return; end if;
  for r in select user_id from public.bridge_members where p_kind = 'bridge' and bridge_id = p_pod and user_id <> me
           union all select user_id from public.group_pod_members where p_kind = 'group' and pod_id = p_pod and user_id <> me loop
    begin perform private.remind_check(me, p_kind, p_pod, r.user_id); return next r.user_id;
    exception when others then null; end;
  end loop;
end $$;
create or replace function public.remindable(p_kind text, p_pod uuid) returns setof uuid
language sql stable security invoker set search_path = '' as $$ select private.remindable(p_kind, p_pod) $$;

-- Service role only (Edge Function): validate, reserve the slot, return what the email needs.
create or replace function private.remind_prepare(p_sender uuid, p_kind text, p_pod uuid, p_target uuid, p_dry boolean default false)
returns table (reminder_id bigint, email text, sender_name text, clip_title text)
language plpgsql security definer set search_path = '' as $$
declare t text; rid bigint;
begin
  t := private.remind_check(p_sender, p_kind, p_pod, p_target);
  if not p_dry then
    insert into public.pod_reminders (sender, target, pod_kind, pod_id) values (p_sender, p_target, p_kind, p_pod) returning id into rid;
  end if;
  return query select rid, u.email::text,
    coalesce((select display_name from public.profiles where id = p_sender), 'A friend'), t
    from auth.users u where u.id = p_target;
end $$;

create or replace function private.remind_finish(p_id bigint, p_ok boolean) returns void
language plpgsql security definer set search_path = '' as $$
declare r record;
begin
  select * into r from public.pod_reminders where id = p_id and status = 'pending';
  if not found then return; end if;
  if not p_ok then delete from public.pod_reminders where id = p_id; return; end if;
  update public.pod_reminders set status = 'sent' where id = p_id;
  if r.pod_kind = 'bridge' then
    perform private.notify(r.target, 'reminder', r.sender, r.pod_id, (select clip_title from public.bridges where id = r.pod_id));
  else
    perform private.notify_group(r.target, 'reminder', r.sender, r.pod_id,
      (select title from public.group_pod_clips where pod_id = r.pod_id order by created_at desc, id limit 1));
  end if;
end $$;

revoke all on function private.remind_check(uuid, text, uuid, uuid) from public, anon, authenticated;
revoke all on function private.remind_prepare(uuid, text, uuid, uuid, boolean) from public, anon, authenticated;
revoke all on function private.remind_finish(bigint, boolean) from public, anon, authenticated;
grant execute on function private.remind_prepare(uuid, text, uuid, uuid, boolean) to service_role;
grant execute on function private.remind_finish(bigint, boolean) to service_role;
grant usage on schema private to service_role;
revoke all on function private.remindable(text, uuid) from public, anon;
grant execute on function private.remindable(text, uuid) to authenticated;
revoke all on function public.remindable(text, uuid) from public, anon;
grant execute on function public.remindable(text, uuid) to authenticated;

-- PostgREST only exposes "public": thin wrappers, executable by the service role only.
create or replace function public.remind_prepare(p_sender uuid, p_kind text, p_pod uuid, p_target uuid, p_dry boolean default false)
returns table (reminder_id bigint, email text, sender_name text, clip_title text)
language sql security invoker set search_path = '' as $$ select * from private.remind_prepare(p_sender, p_kind, p_pod, p_target, p_dry) $$;
create or replace function public.remind_finish(p_id bigint, p_ok boolean) returns void
language sql security invoker set search_path = '' as $$ select private.remind_finish(p_id, p_ok) $$;
revoke all on function public.remind_prepare(uuid, text, uuid, uuid, boolean) from public, anon, authenticated;
revoke all on function public.remind_finish(bigint, boolean) from public, anon, authenticated;
grant execute on function public.remind_prepare(uuid, text, uuid, uuid, boolean) to service_role;
grant execute on function public.remind_finish(bigint, boolean) to service_role;
