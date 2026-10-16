-- Pod link cards: cache a clip preview (thumbnail, title, site) on 1:1/duo pods (bridges) and group pod clips so the
-- Pods list and pod views can show compact link cards. Additive and safe on live: new NULLABLE columns, the same
-- column-scoped filter/mask trigger as library_items, a member-only SECURITY DEFINER RPC to fill an empty cache
-- (no direct UPDATE grant), and a YouTube backfill. Rows stay readable only through the existing member-only RLS;
-- invite previews (preview_bridge*) are unchanged and never return these columns.
alter table public.bridges
  add column if not exists thumb_url     text check (thumb_url is null or (thumb_url ~ '^https://[^\s"''<>]+$' and char_length(thumb_url) <= 1000)),
  add column if not exists preview_title text check (preview_title is null or char_length(preview_title) <= 300),
  add column if not exists preview_site  text check (preview_site is null or char_length(preview_site) <= 80),
  add column if not exists preview_at    timestamptz;
alter table public.group_pod_clips
  add column if not exists thumb_url     text check (thumb_url is null or (thumb_url ~ '^https://[^\s"''<>]+$' and char_length(thumb_url) <= 1000)),
  add column if not exists preview_title text check (preview_title is null or char_length(preview_title) <= 300),
  add column if not exists preview_site  text check (preview_site is null or char_length(preview_site) <= 80),
  add column if not exists preview_at    timestamptz;

drop trigger if exists bridges_link_cards on public.bridges;
create trigger bridges_link_cards before insert or update of thumb_url, preview_title, preview_site on public.bridges
  for each row execute function private.tg_link_cards();
drop trigger if exists group_pod_clips_link_cards on public.group_pod_clips;
create trigger group_pod_clips_link_cards before insert or update of thumb_url, preview_title, preview_site on public.group_pod_clips
  for each row execute function private.tg_link_cards();

-- Members fill an EMPTY cache once (set-once: preview_at null). p_kind: 'bridge' | 'group_clip'.
create or replace function public.cache_pod_preview(p_kind text, p_id uuid, p_thumb text, p_title text, p_site text)
returns boolean language plpgsql security definer set search_path = '' as $$
declare n int;
begin
  if (select auth.uid()) is null then raise exception 'Not signed in'; end if;
  if p_thumb is not null and p_thumb !~ '^https://' then p_thumb := null; end if;
  p_title := left(nullif(trim(p_title), ''), 300); p_site := left(nullif(trim(p_site), ''), 80);
  if p_kind = 'bridge' then
    if not private.is_bridge_member(p_id) then raise exception 'Not a member'; end if;
    update public.bridges set thumb_url = p_thumb, preview_title = p_title, preview_site = p_site, preview_at = now()
      where id = p_id and preview_at is null;
  elsif p_kind = 'group_clip' then
    if not exists (select 1 from public.group_pod_clips c where c.id = p_id and private.is_group_member(c.pod_id)) then raise exception 'Not a member'; end if;
    update public.group_pod_clips set thumb_url = p_thumb, preview_title = p_title, preview_site = p_site, preview_at = now()
      where id = p_id and preview_at is null;
  else raise exception 'Bad kind'; end if;
  get diagnostics n = row_count; return n > 0;
end $$;
revoke all on function public.cache_pod_preview(text, uuid, text, text, text) from public, anon;
grant execute on function public.cache_pod_preview(text, uuid, text, text, text) to authenticated;

-- Backfill YouTube clips (thumbnail derived from the video id).
update public.bridges b set thumb_url = 'https://img.youtube.com/vi/' || y.vid || '/hqdefault.jpg', preview_site = 'YouTube', preview_at = now()
from (select id, coalesce(
        substring(clip_url from '^https?://(?:www\.)?youtu\.be/([A-Za-z0-9_-]{11})'),
        substring(clip_url from '^https?://(?:www\.|m\.|music\.)?youtube\.com/watch\?(?:[^#]*&)?v=([A-Za-z0-9_-]{11})'),
        substring(clip_url from '^https?://(?:www\.|m\.)?youtube\.com/(?:shorts|embed|live)/([A-Za-z0-9_-]{11})')) vid
      from public.bridges) y
where y.id = b.id and y.vid is not null and b.preview_at is null;
update public.group_pod_clips g set thumb_url = 'https://img.youtube.com/vi/' || y.vid || '/hqdefault.jpg', preview_site = 'YouTube', preview_at = now()
from (select id, coalesce(
        substring(url from '^https?://(?:www\.)?youtu\.be/([A-Za-z0-9_-]{11})'),
        substring(url from '^https?://(?:www\.|m\.|music\.)?youtube\.com/watch\?(?:[^#]*&)?v=([A-Za-z0-9_-]{11})'),
        substring(url from '^https?://(?:www\.|m\.)?youtube\.com/(?:shorts|embed|live)/([A-Za-z0-9_-]{11})')) vid
      from public.group_pod_clips) y
where y.id = g.id and y.vid is not null and g.preview_at is null;
-- Non-YouTube pods: copy a cached Library preview for the same URL (from the pod creator's own library row).
update public.bridges b set thumb_url = l.thumb_url, preview_title = l.preview_title, preview_site = l.preview_site, preview_at = l.preview_at
from public.library_items l where b.preview_at is null and l.preview_at is not null and l.url = b.clip_url and l.user_id = b.created_by;
update public.group_pod_clips g set thumb_url = l.thumb_url, preview_title = l.preview_title, preview_site = l.preview_site, preview_at = l.preview_at
from public.library_items l where g.preview_at is null and l.preview_at is not null and l.url = g.url and l.user_id = g.shared_by;
