-- Profile photos.
-- Additive / non-destructive: one nullable column, one Storage bucket + policies, read-only RPCs,
-- a wider reasons list for reports, and delete_my_account() now insists the photo files are gone first.
--
-- Storage design
--   * Bucket 'avatars' is PUBLIC so <img src> works everywhere (web, Capacitor, CDN-cached) without signed URLs.
--     Files live at avatars/<user_id>/<random>.(webp|jpg|png); the random part is new for every upload, so URLs
--     aren't guessable. Nobody can LIST another user's folder (no policy allows it), and the path is only handed out
--     through avatars()/invite_avatar(), which follow the same visibility rules as names (signed in, not across a block).
--   * Server-side limits: 2 MB per file, image/jpeg|png|webp only (bucket settings), at most 3 files per user
--     (upload-then-delete-old replace flow needs 2 at a time).
--   * Writes: a signed-in user may insert / update / delete only inside their own folder.
--   * Hosted Storage forbids deleting objects with SQL (storage.protect_delete), so files are removed through the
--     Storage API by the app; delete_my_account() refuses while any of the caller's photo files remain.

-- ------------------------------------------------------------------ bucket
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('avatars', 'avatars', true, 2097152, array['image/jpeg', 'image/png', 'image/webp'])
on conflict (id) do update set public = excluded.public, file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

-- number of photo files a user has (security definer: used inside storage.objects policies without recursion)
create function private.avatar_file_count(p_user uuid) returns int
language sql stable security definer set search_path = '' as $$
  select count(*)::int from storage.objects o where o.bucket_id = 'avatars' and split_part(o.name, '/', 1) = p_user::text;
$$;
create function private.avatar_file_exists(p_path text) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from storage.objects o where o.bucket_id = 'avatars' and o.name = p_path);
$$;
revoke execute on function private.avatar_file_count(uuid), private.avatar_file_exists(text) from public, anon;
grant execute on function private.avatar_file_count(uuid), private.avatar_file_exists(text) to authenticated;

create policy "avatars: read own folder" on storage.objects for select to authenticated
  using (bucket_id = 'avatars' and split_part(name, '/', 1) = (select auth.uid())::text);
create policy "avatars: upload to own folder" on storage.objects for insert to authenticated
  with check (bucket_id = 'avatars'
              and name ~ ('^' || (select auth.uid())::text || '/[a-z0-9-]{8,64}\.(webp|jpg|png)$')
              and private.avatar_file_count((select auth.uid())) < 3);
create policy "avatars: replace own files" on storage.objects for update to authenticated
  using (bucket_id = 'avatars' and split_part(name, '/', 1) = (select auth.uid())::text)
  with check (bucket_id = 'avatars' and name ~ ('^' || (select auth.uid())::text || '/[a-z0-9-]{8,64}\.(webp|jpg|png)$'));
create policy "avatars: delete own files" on storage.objects for delete to authenticated
  using (bucket_id = 'avatars' and split_part(name, '/', 1) = (select auth.uid())::text);

-- ------------------------------------------------------------------ profile column
-- Relative path inside the bucket + ?v=<ms> cache-buster; must point into the owner's own folder.
alter table public.profiles add column avatar_url text;
alter table public.profiles add constraint profiles_avatar_url_format check (
  avatar_url is null or avatar_url ~ ('^' || id::text || '/[a-z0-9-]{8,64}\.(webp|jpg|png)\?v=[0-9]{10,15}$'));
grant update (avatar_url) on public.profiles to authenticated;

create function private.tg_avatar_exists() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.avatar_url is not null and new.avatar_url is distinct from old.avatar_url
     and not private.avatar_file_exists(split_part(new.avatar_url, '?', 1)) then
    raise exception 'Upload the photo first' using errcode = '23514';
  end if;
  return new;
end $$;
revoke execute on function private.tg_avatar_exists() from public, anon, authenticated;
create trigger profiles_avatar_exists before update of avatar_url on public.profiles
  for each row execute function private.tg_avatar_exists();

-- ------------------------------------------------------------------ read RPCs
-- Photos for a batch of people (same visibility as names: signed in, not across a block). At most 200 ids.
create function private.avatars(p_ids uuid[]) returns table (id uuid, avatar_url text)
language sql stable security definer set search_path = '' as $$
  select p.id, p.avatar_url from public.profiles p
  where auth.uid() is not null and p.avatar_url is not null
    and p.id = any ((p_ids)[1:200])
    and (p.id = auth.uid() or not private.is_blocked(auth.uid(), p.id));
$$;
create function public.avatars(p_ids uuid[]) returns table (id uuid, avatar_url text)
language sql stable security invoker set search_path = '' as $$ select * from private.avatars(p_ids); $$;

-- Photo of the person who sent an invite (shown on the invite landing next to their name, like preview_bridge).
create function private.invite_avatar(p_token text) returns text
language sql stable security definer set search_path = '' as $$
  select p.avatar_url from public.bridges b
  join public.bridge_members m on m.bridge_id = b.id and m.role = 'owner'
  join public.profiles p on p.id = m.user_id
  where b.invite_token = p_token and b.partner_left_at is null
    and (auth.uid() is null or not private.is_blocked(auth.uid(), p.id));
$$;
create function public.invite_avatar(p_token text) returns text
language sql stable security invoker set search_path = '' as $$ select private.invite_avatar(p_token); $$;

revoke execute on function private.avatars(uuid[]), public.avatars(uuid[]),
  private.invite_avatar(text), public.invite_avatar(text) from public, anon, authenticated;
grant execute on function private.avatars(uuid[]), public.avatars(uuid[]) to authenticated;
grant execute on function private.invite_avatar(text), public.invite_avatar(text) to anon, authenticated;

-- ------------------------------------------------------------------ reports: "inappropriate photo"
alter table public.reports drop constraint reports_reason_check;
alter table public.reports add constraint reports_reason_check check (reason in
  ('spam', 'harassment', 'hate', 'sexual', 'violence', 'self_harm', 'illegal', 'impersonation', 'inappropriate_photo', 'other'));

create or replace function private.report_content(p_type text, p_id text, p_reason text, p_note text default '')
returns bigint
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); tu uuid; snap text; rid bigint;
begin
  if me is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  if (select count(*) from public.reports where reporter = me and created_at > now() - interval '1 day') >= 30 then
    raise exception 'Too many reports today. Please email bridgeappllc@gmail.com.' using errcode = 'P0001'; end if;
  if p_type = 'user' then
    -- the snapshot keeps the photo path so a moderator can find the file
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

-- ------------------------------------------------------------------ account deletion
-- The app first deletes the photo files through the Storage API (that removes the stored bytes, which SQL can't),
-- then calls this. Refusing while files remain guarantees no photo outlives the account.
create or replace function private.delete_my_account() returns void
language plpgsql security definer set search_path = '' as $$
declare uid uuid := auth.uid();
begin
  if uid is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  if private.avatar_file_count(uid) > 0 then
    raise exception 'Please remove your profile photo first' using errcode = 'P0001', hint = 'avatar_files_remaining';
  end if;
  delete from auth.users where id = uid;
end $$;
