-- Invite landing without the clip link (additive, safe on live). The clip URL is only returned to members;
-- non-members (people who haven't signed up + joined yet) get the title only. public.preview_bridge stays for
-- the current live client; revoke it once every client uses v2.
create or replace function private.preview_bridge_v2(p_token text)
returns table (owner_name text, clip_title text, clip_url text, clip_type text, member_count int, is_member boolean, bridge_id uuid)
language sql stable security definer set search_path = '' as $$
  select p.owner_name, p.clip_title, case when p.is_member then p.clip_url end, p.clip_type, p.member_count, p.is_member, p.bridge_id
  from private.preview_bridge(p_token) p;
$$;
create or replace function public.preview_bridge_v2(p_token text)
returns table (owner_name text, clip_title text, clip_url text, clip_type text, member_count int, is_member boolean, bridge_id uuid)
language sql stable security invoker set search_path = '' as $$ select * from private.preview_bridge_v2(p_token) $$;
revoke all on function private.preview_bridge_v2(text), public.preview_bridge_v2(text) from public;
grant execute on function private.preview_bridge_v2(text), public.preview_bridge_v2(text) to anon, authenticated;
