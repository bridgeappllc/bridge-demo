-- Tips attached to an invite / shared clip (additive). Used by tips2-checkout for apps in TIPS_INVITE_ONLY_APPS
-- (preview first); the existing tips2_prepare is unchanged, so the live app keeps working as before.
--   * Only listening tips: a tip must name a clip (bridge or group pod clip) that the tipper is in. Every pod clip
--     carries the pod's question, and the tip is held until the recipient answers it.
--   * Recipient = a member who hasn't answered yet, OR the person a one-friend pod was sent to directly while that
--     invite is still pending (they earn it by accepting, listening and answering).
create or replace function private.tip2_invited(p_kind text, p_ref uuid, p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select p_kind = 'bridge' and exists (select 1 from public.bridges b where b.id = p_ref and b.direct_to = p_user and b.direct_status = 'pending') $$;
revoke all on function private.tip2_invited(text, uuid, uuid) from public, anon, authenticated;

create or replace function public.tips2_prepare_invite(p_tipper uuid, p_recipient uuid, p_kind text, p_ref uuid)
returns table (stripe_account_id text, recipient_name text, tipper_name text, title text)
language plpgsql stable security definer set search_path = '' as $$
declare rn text; tn text; t text;
begin
  if p_tipper is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  if p_kind is null or p_kind not in ('bridge','group_clip') or p_ref is null then raise exception 'Tips go with a clip you share. Add one when you invite someone to a pod or share a clip' using errcode = 'P0001'; end if;
  if p_recipient is null or p_recipient = p_tipper then raise exception 'You can''t tip yourself' using errcode = 'P0001'; end if;
  select display_name into tn from public.profiles where id = p_tipper;
  if tn is null then raise exception 'Finish setting up your profile first' using errcode = 'P0001'; end if;
  select display_name into rn from public.profiles where id = p_recipient;
  if rn is null or private.is_blocked(p_tipper, p_recipient) then raise exception 'Person not found' using errcode = 'P0001'; end if;
  if p_kind = 'bridge' then select b.clip_title into t from public.bridges b where b.id = p_ref;
  else select c.title into t from public.group_pod_clips c where c.id = p_ref; end if;
  if t is null or not private.tip2_member(p_kind, p_ref, p_tipper) then raise exception 'Pod not found' using errcode = 'P0001'; end if;
  if not (private.tip2_member(p_kind, p_ref, p_recipient) or private.tip2_invited(p_kind, p_ref, p_recipient)) then raise exception '% isn''t in this pod', rn using errcode = 'P0001'; end if;
  if private.tip2_answered(p_kind, p_ref, p_recipient) then raise exception '% already answered this one', rn using errcode = 'P0001'; end if;
  return query select null::text, rn, tn, t;
end $$;
revoke all on function public.tips2_prepare_invite(uuid, uuid, text, uuid) from public, anon, authenticated;
grant execute on function public.tips2_prepare_invite(uuid, uuid, text, uuid) to service_role;

-- Sweep: a held tip on a still-pending direct invite isn't refunded early (still 30 days max); declined -> refunded.
create or replace function public.tips2_refundable() returns setof public.tips2
language sql stable security definer set search_path = '' as $$
  select * from public.tips2 t where t.mode = 'platform' and t.payment_intent_id is not null and (
    (t.status = 'held' and (t.paid_at < now() - interval '30 days' or t.recipient is null
                            or not (private.tip2_member(t.pod_kind, t.pod_ref, t.recipient) or private.tip2_invited(t.pod_kind, t.pod_ref, t.recipient))))
    or (t.status = 'earned' and (t.earned_at < now() - interval '90 days' or t.recipient is null)))
$$;
revoke all on function public.tips2_refundable() from public, anon, authenticated;
grant execute on function public.tips2_refundable() to service_role;
