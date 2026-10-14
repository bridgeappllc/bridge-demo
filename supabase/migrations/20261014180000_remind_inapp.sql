-- Remind v2 (additive, safe on live): anyone who hasn't answered can be reminded, including the pending
-- recipient of a direct send. The in-app notification always goes out; email only when the target has a
-- confirmed, non-guest email with reminders on. Same blocks + limits. Signatures unchanged; remind_prepare
-- now returns email = null when the reminder is in-app only.
create or replace function private.remind_check(p_sender uuid, p_kind text, p_pod uuid, p_target uuid) returns text
language plpgsql stable security definer set search_path = '' as $$
declare t text; ok boolean;
begin
  if p_sender is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  if p_target = p_sender then raise exception 'You can''t remind yourself' using errcode = 'P0001'; end if;
  if p_kind = 'bridge' then
    if not exists (select 1 from public.bridge_members where bridge_id = p_pod and user_id = p_sender) then raise exception 'Pod not found' using errcode = 'P0002'; end if;
    select b.clip_title, m.answered_at is null into t, ok from public.bridges b join public.bridge_members m on m.bridge_id = b.id and m.user_id = p_target where b.id = p_pod;
    if t is null then
      -- pending direct send: they haven't accepted yet, so they're not a member
      select b.clip_title, true into t, ok from public.bridges b
        where b.id = p_pod and b.direct_to = p_target and b.direct_status = 'pending' and b.partner_left_at is null;
    end if;
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
  if not exists (select 1 from auth.users u where u.id = p_target and u.deleted_at is null) then
    raise exception 'They''re not in this pod' using errcode = 'P0002'; end if;
  if exists (select 1 from public.pod_reminders where target = p_target and pod_id = p_pod and created_at > now() - interval '24 hours') then
    raise exception 'Already reminded in the last 24 hours' using errcode = 'P0001'; end if;
  if (select count(*) from public.pod_reminders where sender = p_sender and created_at > now() - interval '24 hours') >= 10 then
    raise exception 'You''ve sent 10 reminders today — try again tomorrow' using errcode = 'P0001'; end if;
  return t;
end $$;

create or replace function private.remind_emailable(p_target uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from auth.users u join public.profiles p on p.id = u.id
    where u.id = p_target and u.email is not null and u.email_confirmed_at is not null
      and not coalesce(u.is_anonymous, false) and u.deleted_at is null and p.email_reminders) $$;

create or replace function private.remindable(p_kind text, p_pod uuid) returns setof uuid
language plpgsql stable security definer set search_path = '' as $$
declare me uuid := auth.uid(); r record;
begin
  if me is null then return; end if;
  for r in select user_id from public.bridge_members where p_kind = 'bridge' and bridge_id = p_pod and user_id <> me
           union select direct_to from public.bridges where p_kind = 'bridge' and id = p_pod and direct_status = 'pending' and direct_to is not null and direct_to <> me
           union select user_id from public.group_pod_members where p_kind = 'group' and pod_id = p_pod and user_id <> me loop
    begin perform private.remind_check(me, p_kind, p_pod, r.user_id); return next r.user_id;
    exception when others then null; end;
  end loop;
end $$;

create or replace function private.remind_prepare(p_sender uuid, p_kind text, p_pod uuid, p_target uuid, p_dry boolean default false)
returns table (reminder_id bigint, email text, sender_name text, clip_title text)
language plpgsql security definer set search_path = '' as $$
declare t text; rid bigint;
begin
  t := private.remind_check(p_sender, p_kind, p_pod, p_target);
  if not p_dry then
    insert into public.pod_reminders (sender, target, pod_kind, pod_id) values (p_sender, p_target, p_kind, p_pod) returning id into rid;
  end if;
  return query select rid,
    case when private.remind_emailable(p_target) then (select u.email::text from auth.users u where u.id = p_target) end,
    coalesce((select display_name from public.profiles where id = p_sender), 'A friend'), t;
end $$;

revoke all on function private.remind_emailable(uuid) from public, anon, authenticated;
revoke all on function private.remind_check(uuid, text, uuid, uuid) from public, anon, authenticated;
revoke all on function private.remind_prepare(uuid, text, uuid, uuid, boolean) from public, anon, authenticated;
grant execute on function private.remind_prepare(uuid, text, uuid, uuid, boolean) to service_role;
revoke all on function private.remindable(text, uuid) from public, anon;
grant execute on function private.remindable(text, uuid) to authenticated;
