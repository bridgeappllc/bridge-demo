-- Content filter (Apple Guideline 1.2): hate terms / slurs are blocked everywhere;
-- general profanity is BLOCKED in names, @usernames and bios and MASKED (f***) in chat,
-- bridge answers and library titles/notes/creators.
--
-- Additive and non-destructive:
--   * one new table (public.moderation_terms — the editable word list), one read-only RPC,
--   * BEFORE INSERT/UPDATE triggers that only look at NEW / CHANGED values.
-- Existing rows are never rewritten; an UPDATE that doesn't touch a filtered column is never blocked.
-- How to edit the list: see docs/MODERATION.md.

-- ------------------------------------------------------------------ word list
create table public.moderation_terms (
  term       text primary key
             check (term ~ '^[a-z]+( [a-z]+)*$' and char_length(term) between 2 and 40),
  category   text not null check (category in ('hate', 'profanity')),
  -- word     = the whole word only (letters may repeat: "fuuuck"; leetspeak is normalised first)
  -- stem     = the word plus a common ending: s es ed er ers ing in y ies z
  -- anywhere = anywhere inside a word (only for terms that never occur inside innocent words)
  match      text not null default 'word' check (match in ('word', 'stem', 'anywhere')),
  note       text not null default '',
  created_at timestamptz not null default now(),
  -- multi-word phrases can only be blocked (masking works word by word)
  constraint moderation_terms_phrase_is_hate check (category = 'hate' or term !~ ' '),
  constraint moderation_terms_phrase_is_word check (match = 'word' or term !~ ' '),
  pattern    text generated always as (
    case match when 'anywhere' then '' else '(^| )' end
    || regexp_replace(term, '([a-z])', '\1+', 'g')
    || case match when 'stem' then '(s|es|ed|er|ers|ing|in|y|ies|z)?' else '' end
    || case match when 'anywhere' then '' else '( |$)' end
  ) stored
);
comment on table public.moderation_terms is
  'Content filter word list. category: hate = always blocked; profanity = blocked in names/usernames/bios, masked in chat/answers/library. match: word | stem | anywhere. See docs/MODERATION.md.';
alter table public.moderation_terms enable row level security;   -- no policies: clients can't read/write it directly
revoke all on public.moderation_terms from anon, authenticated;

insert into public.moderation_terms (term, category, match, note) values
  -- hate: slurs, hate slogans, self-harm harassment (always blocked)
  ('nigger', 'hate', 'stem', ''), ('nigga', 'hate', 'stem', ''), ('sandnigger', 'hate', 'stem', ''),
  ('kike', 'hate', 'stem', ''), ('spic', 'hate', 'word', 'not stem: spicy'), ('spics', 'hate', 'word', ''),
  ('wetback', 'hate', 'stem', ''), ('beaner', 'hate', 'stem', ''), ('gook', 'hate', 'stem', ''),
  ('raghead', 'hate', 'stem', ''), ('towelhead', 'hate', 'stem', ''), ('jigaboo', 'hate', 'stem', ''),
  ('porch monkey', 'hate', 'word', ''), ('paki', 'hate', 'stem', ''),
  ('faggot', 'hate', 'stem', ''), ('fag', 'hate', 'word', 'not stem: Fagin'), ('fags', 'hate', 'word', ''), ('tranny', 'hate', 'stem', ''), ('trannies', 'hate', 'word', ''),
  ('retard', 'hate', 'word', 'not stem: retarding (technical)'), ('retards', 'hate', 'word', ''), ('retarded', 'hate', 'word', ''),
  ('heil hitler', 'hate', 'word', ''), ('sieg heil', 'hate', 'word', ''), ('white power', 'hate', 'word', ''),
  ('gas the jews', 'hate', 'word', ''),
  ('kys', 'hate', 'word', 'kill yourself'), ('kill yourself', 'hate', 'word', ''), ('kill urself', 'hate', 'word', ''),
  ('kill your self', 'hate', 'word', ''),
  -- profanity (masked in chat/answers/library; blocked in names, @usernames, bios)
  ('fuck', 'profanity', 'anywhere', 'also motherfucker, fuckface...'), ('fuk', 'profanity', 'stem', ''), ('fck', 'profanity', 'stem', ''),
  ('shit', 'profanity', 'stem', ''), ('bullshit', 'profanity', 'stem', ''), ('horseshit', 'profanity', 'stem', ''),
  ('shithead', 'profanity', 'stem', ''), ('shithole', 'profanity', 'stem', ''),
  ('bitch', 'profanity', 'stem', ''), ('cunt', 'profanity', 'stem', ''),
  ('ass', 'profanity', 'stem', ''), ('asshole', 'profanity', 'stem', ''), ('arse', 'profanity', 'stem', ''),
  ('arsehole', 'profanity', 'stem', ''), ('jackass', 'profanity', 'stem', ''), ('dickhead', 'profanity', 'stem', ''),
  ('cock', 'profanity', 'word', 'not stem: cocky'), ('cocksucker', 'profanity', 'stem', ''),
  ('pussy', 'profanity', 'word', ''), ('pussies', 'profanity', 'word', ''),
  ('bastard', 'profanity', 'stem', ''), ('slut', 'profanity', 'stem', ''), ('whore', 'profanity', 'stem', ''),
  ('twat', 'profanity', 'stem', ''), ('wank', 'profanity', 'stem', ''), ('wanker', 'profanity', 'stem', ''),
  ('piss', 'profanity', 'stem', ''), ('douchebag', 'profanity', 'stem', ''),
  ('jizz', 'profanity', 'stem', ''), ('dildo', 'profanity', 'stem', ''), ('tits', 'profanity', 'word', ''),
  ('titties', 'profanity', 'word', '')
on conflict (term) do nothing;

-- ------------------------------------------------------------------ matching
-- Normalise: lowercase; "!" or "|" between letters -> i (sh!t); leetspeak 0 1 3 4 5 7 @ $ -> o i e a s t a s;
-- everything that isn't a-z becomes a single space. Mirrored exactly by MOD.norm() in index.html.
create function private.mod_norm(p text) returns text
language sql immutable set search_path = '' as $$
  select btrim(regexp_replace(
           translate(regexp_replace(lower(coalesce(p, '')), '([a-z0-9@$])[!|]+(?=[a-z0-9@$])', '\1i', 'g'),
                     '013457@$', 'oieastas'),
           '[^a-z]+', ' ', 'g'));
$$;

-- 'hate', 'profanity' or null (worst match wins)
create function private.mod_scan(p text) returns text
language sql stable security definer set search_path = '' as $$
  select case
    when p is null or btrim(p) = '' then null
    when exists (select 1 from public.moderation_terms t where t.category = 'hate' and x.n ~ t.pattern) then 'hate'
    when exists (select 1 from public.moderation_terms t where t.category = 'profanity' and x.n ~ t.pattern) then 'profanity'
  end
  from (select ' ' || private.mod_norm(p) || ' ' as n) x;
$$;

-- Replace each word containing profanity with its first character + asterisks; everything else is kept as typed.
create function private.mod_mask(p text) returns text
language plpgsql stable security definer set search_path = '' as $$
declare
  r text := '';
  m text[];
begin
  if p is null or private.mod_scan(p) is distinct from 'profanity' then return p; end if;
  for m in select regexp_matches(p, '([A-Za-z0-9@$]+(?:[!|]+[A-Za-z0-9@$]+)*)|(.)', 'g') loop
    if m[1] is not null and exists (
         select 1 from public.moderation_terms t
         where t.category = 'profanity' and (' ' || private.mod_norm(m[1]) || ' ') ~ t.pattern) then
      r := r || left(m[1], 1) || repeat('*', char_length(m[1]) - 1);
    else
      r := r || coalesce(m[1], m[2]);
    end if;
  end loop;
  return r;
end $$;

-- block = any match (names); hate_only = slurs only (masked fields)
create function private.mod_reject(p text, p_field text, p_block_profanity boolean) returns void
language plpgsql stable set search_path = '' as $$
declare v text := private.mod_scan(p);
begin
  if v = 'hate' or (v = 'profanity' and p_block_profanity) then
    raise exception using errcode = '23514', message = 'Please keep it respectful', detail = 'content_filter:' || p_field;
  end if;
end $$;

-- ------------------------------------------------------------------ triggers (new/changed values only)
create function private.tg_mod_profiles() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'INSERT' or new.display_name is distinct from old.display_name then
    perform private.mod_reject(new.display_name, 'display_name', true); end if;
  if tg_op = 'INSERT' or new.username is distinct from old.username then
    perform private.mod_reject(new.username, 'username', true); end if;
  if tg_op = 'INSERT' or new.bio is distinct from old.bio then
    perform private.mod_reject(new.bio, 'bio', true); end if;
  return new;
end $$;
create trigger profiles_content_filter before insert or update of display_name, username, bio on public.profiles
  for each row execute function private.tg_mod_profiles();

create function private.tg_mod_bridge_members() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'INSERT' or new.display_name is distinct from old.display_name then
    perform private.mod_reject(new.display_name, 'display_name', true); end if;
  return new;
end $$;
create trigger bridge_members_content_filter before insert or update of display_name on public.bridge_members
  for each row execute function private.tg_mod_bridge_members();

create function private.tg_mod_messages() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'INSERT' or new.body is distinct from old.body then
    perform private.mod_reject(new.body, 'body', false);
    new.body := private.mod_mask(new.body);
  end if;
  return new;
end $$;
create trigger messages_content_filter before insert or update of body on public.messages
  for each row execute function private.tg_mod_messages();

create function private.tg_mod_answers() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'INSERT' or new.a1 is distinct from old.a1 then
    perform private.mod_reject(new.a1, 'a1', false); new.a1 := private.mod_mask(new.a1); end if;
  if tg_op = 'INSERT' or new.a2 is distinct from old.a2 then
    perform private.mod_reject(new.a2, 'a2', false); new.a2 := private.mod_mask(new.a2); end if;
  if tg_op = 'INSERT' or new.a3 is distinct from old.a3 then
    perform private.mod_reject(new.a3, 'a3', false); new.a3 := private.mod_mask(new.a3); end if;
  return new;
end $$;
create trigger answers_content_filter before insert or update of a1, a2, a3 on public.answers
  for each row execute function private.tg_mod_answers();

create function private.tg_mod_library_items() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'INSERT' or new.title is distinct from old.title then
    perform private.mod_reject(new.title, 'title', false); new.title := private.mod_mask(new.title); end if;
  if tg_op = 'INSERT' or new.note is distinct from old.note then
    perform private.mod_reject(new.note, 'note', false); new.note := private.mod_mask(new.note); end if;
  if tg_op = 'INSERT' or new.creator is distinct from old.creator then
    perform private.mod_reject(new.creator, 'creator', false); new.creator := private.mod_mask(new.creator); end if;
  return new;
end $$;
create trigger library_items_content_filter before insert or update of title, note, creator on public.library_items
  for each row execute function private.tg_mod_library_items();

-- ------------------------------------------------------------------ client copy of the list
-- The app downloads the patterns once to give instant inline errors; the triggers above are the real enforcement.
create function private.moderation_terms_list() returns table (term text, category text, match text, pattern text)
language sql stable security definer set search_path = '' as $$
  select t.term, t.category, t.match, t.pattern from public.moderation_terms t order by t.category, t.term;
$$;
create function public.moderation_terms_list() returns table (term text, category text, match text, pattern text)
language sql stable security invoker set search_path = '' as $$ select * from private.moderation_terms_list(); $$;

-- privileges: triggers run as the writing user, so authenticated needs EXECUTE on the helpers
-- (they're in the private schema, which PostgREST doesn't expose). The list RPC is readable before sign-in too.
revoke execute on function private.mod_norm(text), private.mod_scan(text), private.mod_mask(text),
  private.mod_reject(text, text, boolean), private.moderation_terms_list(),
  private.tg_mod_profiles(), private.tg_mod_bridge_members(), private.tg_mod_messages(),
  private.tg_mod_answers(), private.tg_mod_library_items() from public, anon, authenticated;
grant execute on function private.mod_norm(text), private.mod_scan(text), private.mod_mask(text),
  private.mod_reject(text, text, boolean) to authenticated;
grant execute on function private.moderation_terms_list() to anon, authenticated;
revoke execute on function public.moderation_terms_list() from public;
grant execute on function public.moderation_terms_list() to anon, authenticated;

-- Admin helper (SQL editor only): which EXISTING rows would match today? Read-only; nothing is changed.
create view private.content_filter_existing_matches with (security_invoker = true) as
  select 'profiles.display_name' as field, id::text as row_id, private.mod_scan(display_name) as verdict, display_name as value from public.profiles where private.mod_scan(display_name) is not null
  union all select 'profiles.username', id::text, private.mod_scan(username), username from public.profiles where private.mod_scan(username) is not null
  union all select 'profiles.bio', id::text, private.mod_scan(bio), bio from public.profiles where private.mod_scan(bio) is not null
  union all select 'bridge_members.display_name', bridge_id::text || '/' || user_id::text, private.mod_scan(display_name), display_name from public.bridge_members where private.mod_scan(display_name) is not null
  union all select 'messages.body', id::text, private.mod_scan(body), body from public.messages where private.mod_scan(body) is not null
  union all select 'answers', bridge_id::text || '/' || user_id::text, private.mod_scan(a1 || ' . ' || a2 || ' . ' || a3), left(a1 || ' | ' || a2 || ' | ' || a3, 300) from public.answers where private.mod_scan(a1 || ' . ' || a2 || ' . ' || a3) is not null
  union all select 'library_items.title/note/creator', id::text, private.mod_scan(title || ' . ' || note || ' . ' || creator), left(title || ' | ' || note || ' | ' || creator, 300) from public.library_items where private.mod_scan(title || ' . ' || note || ' . ' || creator) is not null;
revoke all on private.content_filter_existing_matches from public, anon, authenticated;
