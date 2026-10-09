-- =====================================================================
-- Bridge v3 — remove the rating step. Flow is now Invite → Answer → Talk.
--  * Chat (read + write) opens as soon as YOU have submitted your answers.
--    You still see the other person's answers only after submitting yours.
--  * public.ratings is kept with its rows (no data is deleted) but is retired:
--    no API role can read or write it, and it's no longer broadcast by Realtime.
--  * The community-ratings aggregate is removed.
-- No rows are modified. Existing bridges move forward automatically: anyone who
-- answered (rated or not) now has chat access.
-- =====================================================================

-- chat: unlock on answers instead of rating
drop policy "members read chat after rating" on public.messages;
drop policy "members chat after rating" on public.messages;
create policy "members read chat after answering" on public.messages for select to authenticated
  using (private.is_bridge_member(bridge_id) and private.has_answered(bridge_id));
create policy "members chat after answering" on public.messages for insert to authenticated
  with check (user_id = (select auth.uid()) and private.is_bridge_member(bridge_id) and private.has_answered(bridge_id));

-- ratings: keep the table and data, stop exposing/using it
drop policy "read own rating, or friend's after rating" on public.ratings;
drop policy "members rate after answering" on public.ratings;
revoke all on public.ratings from anon, authenticated;
drop trigger ratings_mark on public.ratings;
drop function private.tg_mark_rated();
drop function private.has_rated(uuid);
comment on table public.ratings is 'Retired Oct 2026 (rating step removed). Kept for history; not readable or writable through the API.';
do $$ begin
  if exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'ratings') then
    alter publication supabase_realtime drop table public.ratings;
  end if;
end $$;

-- community ratings (aggregate of bridge ratings) removed
drop function public.community_ratings(text[]);
drop function private.community_ratings(text[]);
