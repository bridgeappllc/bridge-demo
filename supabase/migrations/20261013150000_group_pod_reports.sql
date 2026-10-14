-- Group pod reports: additive. Widens reports.target_type and extends report_content() with group types.
-- Existing types (user, library_item, message) behave exactly as before.
alter table public.reports drop constraint if exists reports_target_type_check;
alter table public.reports add constraint reports_target_type_check check (target_type in
  ('user', 'library_item', 'message', 'group_message', 'group_clip', 'group_pod'));

create or replace function private.report_content(p_type text, p_id text, p_reason text, p_note text default '')
returns bigint
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); tu uuid; snap text; rid bigint;
begin
  if me is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  if (select count(*) from public.reports where reporter = me and created_at > now() - interval '1 day') >= 30 then
    raise exception 'Too many reports today. Please email bridgeappllc@gmail.com.' using errcode = 'P0001'; end if;
  if p_type = 'user' then
    select p.id, left(p.display_name || coalesce(' @' || p.username, '') || coalesce(' — ' || nullif(p.bio, ''), '')
                      || coalesce(' — photo: avatars/' || p.avatar_url, ''), 4000)
      into tu, snap from public.profiles p where p.id::text = p_id;
    if p_reason = 'inappropriate_photo' and tu is not null
       and not exists (select 1 from public.profiles p where p.id = tu and p.avatar_url is not null) then
      raise exception 'This person has no profile photo' using errcode = 'P0001'; end if;
  elsif p_reason = 'inappropriate_photo' then
    raise exception 'Only profiles have photos' using errcode = '22023';
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
  elsif p_type = 'group_message' then
    if p_id !~ '^[0-9]{1,18}$' then raise exception 'Not found' using errcode = 'P0002'; end if;
    select m.user_id, left('pod ' || m.pod_id || ': ' || m.body, 4000) into tu, snap from public.group_pod_messages m
     where m.id = p_id::bigint and private.is_group_member(m.pod_id);
  elsif p_type = 'group_clip' then
    if p_id !~ '^[0-9a-f-]{36}$' then raise exception 'Not found' using errcode = 'P0002'; end if;
    select c.shared_by, left('pod ' || c.pod_id || ': ' || c.title || ' — ' || c.url || coalesce(' — note: ' || nullif(c.note, ''), ''), 4000)
      into tu, snap from public.group_pod_clips c where c.id = p_id::uuid and private.is_group_member(c.pod_id);
  elsif p_type = 'group_pod' then
    if p_id !~ '^[0-9a-f-]{36}$' then raise exception 'Not found' using errcode = 'P0002'; end if;
    select g.owner, left('pod ' || g.id || ': ' || g.name, 4000) into tu, snap
      from public.group_pods g where g.id = p_id::uuid and private.is_group_member(g.id);
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
