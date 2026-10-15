-- Link filter: adult/porn links (and URL shorteners that could hide them) can't be shared on Pod Club.
-- Additive, safe on live: new admin-only tables + BEFORE INSERT/UPDATE triggers that only check NEW/CHANGED URLs.
-- Existing rows are never rewritten or deleted. Domain list data: supabase/seed/blocked_domains.sql (see docs/MODERATION.md).

create table if not exists public.blocked_domains (
  domain     text primary key check (domain ~ '^[a-z0-9-]+(\.[a-z0-9-]+)+$' and char_length(domain) <= 253),
  category   text not null default 'adult' check (category in ('adult', 'shortener', 'manual')),
  source     text not null default 'manual',
  created_at timestamptz not null default now()
);
comment on table public.blocked_domains is 'Link filter: a URL is blocked if its host or any parent domain is listed (normalized: lowercase, no www., punycode). See docs/MODERATION.md.';
create table if not exists public.blocked_link_keywords (
  keyword    text primary key check (keyword ~ '^[a-z0-9]{3,30}$'),
  exceptions text[] not null default '{}',   -- substrings removed from the host before matching (e.g. essex for "sex")
  note       text not null default ''
);
comment on table public.blocked_link_keywords is 'Link filter: a URL is blocked if its normalized host contains the keyword (after removing exceptions).';
create table if not exists public.allowed_domains (
  domain text primary key check (domain ~ '^[a-z0-9-]+(\.[a-z0-9-]+)+$'),
  note   text not null default ''
);
comment on table public.allowed_domains is 'Link filter overrides: a host (or parent) listed here is never blocked by the keyword or domain rules.';
alter table public.blocked_domains enable row level security;
alter table public.blocked_link_keywords enable row level security;
alter table public.allowed_domains enable row level security;
revoke all on public.blocked_domains, public.blocked_link_keywords, public.allowed_domains from anon, authenticated;

insert into public.blocked_link_keywords (keyword, exceptions, note) values
  ('porn', '{}', ''), ('xxx', '{}', ''), ('hentai', '{}', ''), ('nsfw', '{}', ''), ('xvideo', '{}', ''),
  ('xhamster', '{}', ''), ('redtube', '{}', ''), ('youporn', '{}', ''), ('camgirl', '{}', ''), ('camsex', '{}', ''),
  ('sexcam', '{}', ''), ('milf', '{}', ''), ('bdsm', '{}', ''), ('onlyfans', '{}', ''), ('fansly', '{}', ''),
  ('nudes', '{}', ''), ('livejasmin', '{}', ''), ('chaturbate', '{}', ''), ('stripchat', '{}', ''),
  ('sex', '{essex,sussex,wessex,middlesex,sexton,sextant,unisex}', 'place names / words containing "sex" are excepted')
on conflict (keyword) do nothing;

insert into public.blocked_domains (domain, category, source) values
  ('bit.ly','shortener','manual'), ('bitly.com','shortener','manual'), ('tinyurl.com','shortener','manual'), ('t.co','shortener','manual'),
  ('goo.gl','shortener','manual'), ('ow.ly','shortener','manual'), ('is.gd','shortener','manual'), ('v.gd','shortener','manual'),
  ('buff.ly','shortener','manual'), ('rebrand.ly','shortener','manual'), ('cutt.ly','shortener','manual'), ('shorturl.at','shortener','manual'),
  ('tiny.cc','shortener','manual'), ('rb.gy','shortener','manual'), ('bl.ink','shortener','manual'), ('t.ly','shortener','manual'),
  ('s.id','shortener','manual'), ('shorte.st','shortener','manual'), ('adf.ly','shortener','manual'), ('ouo.io','shortener','manual'),
  ('bc.vc','shortener','manual'), ('tr.im','shortener','manual'), ('clck.ru','shortener','manual'), ('qr.ae','shortener','manual'),
  ('lnkd.in','shortener','manual'), ('linktr.ee','shortener','manual'), ('shorturl.gg','shortener','manual'), ('tinyurl.is','shortener','manual')
on conflict (domain) do nothing;

-- RFC 3492 punycode for one label (used to normalize internationalized hosts to their xn-- form).
create or replace function private.punycode_label(p text) returns text
language plpgsql immutable set search_path = '' as $$
declare
  cps int[] := '{}'; c int; n int := 128; delta int := 0; bias int := 72; h int; b int; m int; q int; k int; t int;
  out text := ''; i int; first boolean;
begin
  for i in 1..char_length(p) loop cps := cps || ascii(substr(p, i, 1)); end loop;
  foreach c in array cps loop if c < 128 then out := out || chr(c); end if; end loop;
  b := char_length(out); h := b;
  if b = array_length(cps, 1) then return p; end if;
  if b > 0 then out := out || '-'; end if;
  while h < array_length(cps, 1) loop
    m := 2147483647; foreach c in array cps loop if c >= n and c < m then m := c; end if; end loop;
    delta := delta + (m - n) * (h + 1); n := m;
    foreach c in array cps loop
      if c < n then delta := delta + 1; end if;
      if c = n then
        q := delta; k := 36;
        loop
          t := case when k <= bias then 1 when k >= bias + 26 then 26 else k - bias end;
          exit when q < t;
          out := out || chr(case when t + (q - t) % (36 - t) < 26 then 97 + t + (q - t) % (36 - t) else 22 + t + (q - t) % (36 - t) end);
          q := (q - t) / (36 - t); k := k + 36;
        end loop;
        out := out || chr(case when q < 26 then 97 + q else 22 + q end);
        -- adapt bias
        first := (h = b); delta := case when first then delta / 700 else delta / 2 end; delta := delta + delta / (h + 1); k := 0;
        while delta > 455 loop delta := delta / 35; k := k + 36; end loop;
        bias := k + (36 * delta) / (delta + 38); delta := 0; h := h + 1;
      end if;
    end loop;
    delta := delta + 1; n := n + 1;
  end loop;
  return 'xn--' || out;
end $$;

-- Normalized host of a URL: lowercase, no scheme/userinfo/port/path, no trailing dot, no leading www., punycode labels.
create or replace function private.link_host(p_url text) returns text
language plpgsql immutable set search_path = '' as $$
declare u text := lower(btrim(coalesce(p_url, ''))); h text; lbl text; res text[] := '{}';
begin
  u := replace(u, '\', '/');
  u := regexp_replace(u, '^[a-z][a-z0-9+.-]*:/*', '');
  h := split_part(split_part(split_part(u, '/', 1), '?', 1), '#', 1);
  h := regexp_replace(h, '^.*@', '');                                      -- userinfo
  -- percent-decoded host (e.g. %70orn.com); invalid sequences are left as-is
  declare m text[]; bytes bytea := ''::bytea; rest text := h; begin
    if h ~ '%[0-9a-f]{2}' then
      while rest <> '' loop
        m := regexp_match(rest, '^%([0-9a-f]{2})(.*)$');
        if m is not null then bytes := bytes || decode(m[1], 'hex'); rest := m[2];
        else bytes := bytes || convert_to(substr(rest, 1, 1), 'UTF8'); rest := substr(rest, 2); end if;
      end loop;
      h := convert_from(bytes, 'UTF8');
    end if;
  exception when others then null; end;
  h := lower(translate(h, '。．｡', '...'));
  h := regexp_replace(h, ':[0-9]*$', '');                                  -- port
  h := btrim(h, '[].');
  h := regexp_replace(h, '^(www[0-9]*\.)+', '');
  if h = '' then return ''; end if;
  foreach lbl in array string_to_array(h, '.') loop
    if lbl ~ '[^\x00-\x7f]' then lbl := private.punycode_label(lbl); end if;
    res := res || lbl;
  end loop;
  return array_to_string(res, '.');
end $$;

-- Why a URL is blocked ('adult' | 'shortener' | 'manual'), or null if it's fine.
create or replace function private.link_block_reason(p_url text) returns text
language plpgsql stable security definer set search_path = '' as $$
declare h text := private.link_host(p_url); parts text[]; suf text[] := '{}'; i int; r text; k record; hx text; e text;
begin
  if h is null or h = '' then return null; end if;
  parts := string_to_array(h, '.');
  for i in 1..coalesce(array_length(parts, 1), 0) loop suf := suf || array_to_string(parts[i:], '.'); end loop;
  if exists (select 1 from public.allowed_domains a where a.domain = any (suf)) then return null; end if;
  select d.category into r from public.blocked_domains d where d.domain = any (suf)
    order by array_position(suf, d.domain) limit 1;              -- most specific match
  if r is not null then return r; end if;
  for k in select * from public.blocked_link_keywords loop
    hx := h; foreach e in array k.exceptions loop hx := replace(hx, e, ''); end loop;
    if position(k.keyword in hx) > 0 then return 'adult'; end if;
  end loop;
  return null;
end $$;

create or replace function private.link_reject(p_url text, p_field text) returns void
language plpgsql stable security definer set search_path = '' as $$
declare r text := private.link_block_reason(p_url);
begin
  if r is not null then
    raise exception using errcode = '23514', message = 'That link can''t be shared on Pod Club.', detail = 'link_filter:' || r || ':' || p_field;
  end if;
end $$;

-- Instant client-side feedback (the triggers below are the real enforcement).
create or replace function public.link_ok(p_url text) returns boolean
language sql stable security definer set search_path = '' as $$ select private.link_block_reason(left(p_url, 2000)) is null $$;

create or replace function private.tg_link_bridges() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'INSERT' or new.clip_url is distinct from old.clip_url then perform private.link_reject(new.clip_url, 'clip_url'); end if;
  if tg_op = 'INSERT' or new.clip_title is distinct from old.clip_title then
    perform private.mod_reject(new.clip_title, 'clip_title', false); new.clip_title := private.mod_mask(new.clip_title); end if;
  if tg_op = 'INSERT' or new.direct_note is distinct from old.direct_note then
    perform private.mod_reject(new.direct_note, 'direct_note', false); new.direct_note := private.mod_mask(new.direct_note); end if;
  return new;
end $$;
drop trigger if exists bridges_link_filter on public.bridges;
create trigger bridges_link_filter before insert or update of clip_url, clip_title, direct_note on public.bridges
  for each row execute function private.tg_link_bridges();

create or replace function private.tg_link_url() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'INSERT' or new.url is distinct from old.url then perform private.link_reject(new.url, 'url'); end if;
  return new;
end $$;
drop trigger if exists library_items_link_filter on public.library_items;
create trigger library_items_link_filter before insert or update of url on public.library_items for each row execute function private.tg_link_url();
drop trigger if exists group_pod_clips_link_filter on public.group_pod_clips;
create trigger group_pod_clips_link_filter before insert or update of url on public.group_pod_clips for each row execute function private.tg_link_url();

revoke all on function private.punycode_label(text), private.link_host(text), private.link_block_reason(text), private.link_reject(text, text),
  private.tg_link_bridges(), private.tg_link_url() from public, anon, authenticated;
grant execute on function private.punycode_label(text), private.link_host(text), private.link_block_reason(text), private.link_reject(text, text) to authenticated, service_role;
revoke all on function public.link_ok(text) from public;
grant execute on function public.link_ok(text) to anon, authenticated, service_role;
