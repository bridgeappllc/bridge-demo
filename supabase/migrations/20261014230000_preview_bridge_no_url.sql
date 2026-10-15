-- Invite lookup no longer exposes the clip URL to non-members (safe on live: the live app uses preview_bridge_v2).
-- Same signature; preview_bridge now returns clip_url only to members. preview_bridge_v2 keeps working (it reads this).
create or replace function private.preview_bridge(p_token text)
returns table (owner_name text, clip_title text, clip_url text, clip_type text, member_count int, is_member boolean, bridge_id uuid)
language sql stable security definer set search_path = '' as $$
  select coalesce((select m.display_name from public.bridge_members m where m.bridge_id = b.id and m.role = 'owner'), 'Deleted user'),
         b.clip_title,
         case when exists (select 1 from public.bridge_members m where m.bridge_id = b.id and m.user_id = auth.uid()) then b.clip_url end,
         b.clip_type,
         case when b.partner_left_at is not null then 2
              else (select count(*)::int from public.bridge_members m where m.bridge_id = b.id) end,
         exists (select 1 from public.bridge_members m where m.bridge_id = b.id and m.user_id = auth.uid()),
         case when exists (select 1 from public.bridge_members m where m.bridge_id = b.id and m.user_id = auth.uid()) then b.id end
  from public.bridges b where b.invite_token = p_token;
$$;
