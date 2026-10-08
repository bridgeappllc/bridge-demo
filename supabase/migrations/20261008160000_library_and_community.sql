-- =====================================================================
-- Bridge v2 — online library (+ sharing with bridge partners) and
-- community ratings aggregated from bridges. Additive only: no existing
-- table or row is modified.
-- =====================================================================

create table public.library_items (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null default auth.uid() references auth.users(id) on delete cascade,
  url        text not null check (url ~* '^https?://' and char_length(url) <= 2000),
  title      text not null check (char_length(btrim(title)) between 1 and 300),
  category   text not null default '' check (char_length(category) <= 40),
  kind       text not null default 'Article' check (char_length(kind) <= 20),
  creator    text not null default '' check (char_length(creator) <= 120),
  note       text not null default '' check (char_length(note) <= 300),
  created_at timestamptz not null default now(),
  unique (user_id, url)
);

-- true when the caller and `other` are members of at least one common bridge
create function private.shares_bridge_with(other uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.bridge_members a
    join public.bridge_members b on b.bridge_id = a.bridge_id
    where a.user_id = auth.uid() and b.user_id = other);
$$;

alter table public.library_items enable row level security;
create policy "read own library or a bridge partner's" on public.library_items for select to authenticated
  using (user_id = (select auth.uid()) or private.shares_bridge_with(user_id));
create policy "add to own library" on public.library_items for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy "edit own library" on public.library_items for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "remove from own library" on public.library_items for delete to authenticated
  using (user_id = (select auth.uid()));

revoke all on public.library_items from anon, authenticated;
grant select, delete on public.library_items to authenticated;
grant insert (user_id, url, title, category, kind, creator, note) on public.library_items to authenticated;
grant update (title, category, kind, creator, note) on public.library_items to authenticated;

-- Community rating per URL, aggregated over all bridge ratings. Only URLs with
-- >= 3 ratings are returned (so a single person's score is never revealed).
create function private.community_ratings(p_urls text[])
returns table (url text, avg_score numeric, ratings int)
language sql stable security definer set search_path = '' as $$
  select b.clip_url, round(avg(r.score)::numeric, 1), count(*)::int
  from public.ratings r join public.bridges b on b.id = r.bridge_id
  where b.clip_url = any (p_urls[1:200])
  group by b.clip_url
  having count(*) >= 3;
$$;
create function public.community_ratings(p_urls text[])
returns table (url text, avg_score numeric, ratings int)
language sql stable security invoker set search_path = '' as $$
  select * from private.community_ratings(p_urls);
$$;

revoke execute on function private.shares_bridge_with(uuid), private.community_ratings(text[]), public.community_ratings(text[])
  from public, anon, authenticated;
grant execute on function private.shares_bridge_with(uuid), private.community_ratings(text[]), public.community_ratings(text[]) to authenticated;
