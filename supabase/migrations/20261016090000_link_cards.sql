-- Link cards: cache a preview (thumbnail URL, page title, site name) on each library item so the Library can show
-- rich link cards without refetching. Additive and safe on live: new NULLABLE columns, a column-scoped trigger,
-- column grants for the owner (existing RLS "edit own library" policy still applies), and a backfill that only
-- fills the new columns for YouTube links (thumbnail derived from the video id). Existing columns are untouched.
alter table public.library_items
  add column if not exists thumb_url     text check (thumb_url is null or (thumb_url ~ '^https://[^\s"''<>]+$' and char_length(thumb_url) <= 1000)),
  add column if not exists preview_title text check (preview_title is null or char_length(preview_title) <= 300),
  add column if not exists preview_site  text check (preview_site is null or char_length(preview_site) <= 80),
  add column if not exists preview_at    timestamptz;
comment on column public.library_items.thumb_url is 'Link card: cached https thumbnail (og:image / YouTube). Must pass the link filter.';
comment on column public.library_items.preview_at is 'Link card: when the preview was last fetched (null = not yet; set even when nothing was found, so it is not refetched).';

-- The thumbnail host must pass the same adult/shortener link filter as shared links; fetched titles get the word mask.
create or replace function private.tg_link_cards() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.thumb_url is not null and (tg_op = 'INSERT' or new.thumb_url is distinct from old.thumb_url) then
    perform private.link_reject(new.thumb_url, 'thumb_url'); end if;
  if new.preview_title is not null and (tg_op = 'INSERT' or new.preview_title is distinct from old.preview_title) then
    new.preview_title := private.mod_mask(new.preview_title); end if;
  if new.preview_site is not null and (tg_op = 'INSERT' or new.preview_site is distinct from old.preview_site) then
    new.preview_site := private.mod_mask(new.preview_site); end if;
  return new;
end $$;
revoke all on function private.tg_link_cards() from public, anon, authenticated;
drop trigger if exists library_items_link_cards on public.library_items;
create trigger library_items_link_cards before insert or update of thumb_url, preview_title, preview_site on public.library_items
  for each row execute function private.tg_link_cards();

grant insert (thumb_url, preview_title, preview_site, preview_at) on public.library_items to authenticated;
grant update (thumb_url, preview_title, preview_site, preview_at) on public.library_items to authenticated;

-- Backfill YouTube items (youtu.be/<id>, watch?v=<id>, shorts/embed/live/<id>, m./music. hosts).
update public.library_items l set thumb_url = 'https://img.youtube.com/vi/' || y.vid || '/hqdefault.jpg', preview_site = 'YouTube', preview_at = now()
from (select id, coalesce(
        substring(url from '^https?://(?:www\.)?youtu\.be/([A-Za-z0-9_-]{11})'),
        substring(url from '^https?://(?:www\.|m\.|music\.)?youtube\.com/watch\?(?:[^#]*&)?v=([A-Za-z0-9_-]{11})'),
        substring(url from '^https?://(?:www\.|m\.)?youtube\.com/(?:shorts|embed|live)/([A-Za-z0-9_-]{11})')) vid
      from public.library_items) y
where y.id = l.id and y.vid is not null and l.thumb_url is null;
