-- Tips v2 "earn first" (additive only; the live tips flow — tip_accounts, tips, tip_* functions — is untouched).
-- Used by the tips2-* edge functions (preview, Stripe SANDBOX). Kept in separate tables so sandbox account ids never
-- mix with live ones:
--   * Anyone can tip anyone (not self, not blocked). Recipients with a ready account get a destination charge (as before);
--     everyone else is charged on the platform and the 90% is owed to them ("separate charges and transfers").
--   * Listening tips: a pod member adds a tip for another member on a clip; it's 'held' until that member answers the clip,
--     then 'earned'. Thank-you tips on the platform are 'earned' as soon as they're paid.
--   * Earned tips are transferred (source_transaction = the charge) once the recipient's account is payouts-enabled.
--   * Held tips not earned within 30 days (or whose pod/clip is gone) and earned tips unclaimed for 90 days are refunded
--     by the tips2-payout sweep (pg_cron, daily).

create table if not exists public.tip_accounts2 (
  user_id           uuid primary key references auth.users(id) on delete cascade,
  stripe_account_id text not null unique check (stripe_account_id ~ '^acct_[A-Za-z0-9]+$'),
  details_submitted boolean not null default false,
  charges_enabled   boolean not null default false,
  payouts_enabled   boolean not null default false,
  livemode          boolean not null default false,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
alter table public.tip_accounts2 enable row level security;
revoke all on public.tip_accounts2 from anon, authenticated;
grant select on public.tip_accounts2 to authenticated;
drop policy if exists tip_accounts2_owner_reads on public.tip_accounts2;
create policy tip_accounts2_owner_reads on public.tip_accounts2 for select to authenticated using (user_id = (select auth.uid()));

create table if not exists public.tips2 (
  id                 uuid primary key default gen_random_uuid(),
  purpose            text not null default 'thanks' check (purpose in ('thanks','listen')),
  mode               text not null check (mode in ('destination','platform')),
  tipper             uuid references auth.users(id) on delete set null,
  recipient          uuid references auth.users(id) on delete set null,
  tipper_name        text not null default '' check (char_length(tipper_name) <= 40),
  title              text not null default '' check (char_length(title) <= 300),
  pod_kind           text check (pod_kind in ('bridge','group_clip')),
  pod_ref            uuid,
  amount_cents       int not null check (amount_cents between 200 and 10000),
  fee_cents          int not null check (fee_cents >= 0),
  total_cents        int not null check (total_cents = amount_cents + fee_cents),
  app_cut_cents      int not null check (app_cut_cents >= 0),
  recipient_cents    int not null check (recipient_cents = amount_cents - app_cut_cents),   -- amount due to the recipient (90%)
  application_fee_cents int,                                                           -- destination mode only
  stripe_account_id  text,                                                             -- destination mode, or the payout account
  checkout_session_id text unique,
  payment_intent_id  text,
  charge_id          text,
  transfer_id        text unique,
  refund_id          text unique,
  status             text not null default 'pending'
                     check (status in ('pending','held','earned','paying','paid_out','refunding','refunded','failed')),
  livemode           boolean not null default false,
  created_at         timestamptz not null default now(),
  paid_at            timestamptz,
  earned_at          timestamptz,
  paid_out_at        timestamptz,
  refunded_at        timestamptz,
  check (purpose = 'thanks' or (pod_kind is not null and mode = 'platform'))
);
create index if not exists tips2_recipient_idx on public.tips2 (recipient, status);
create index if not exists tips2_tipper_idx on public.tips2 (tipper, created_at desc);
create index if not exists tips2_pod_idx on public.tips2 (pod_kind, pod_ref) where status = 'held';
alter table public.tips2 enable row level security;
revoke all on public.tips2 from anon, authenticated;
grant select on public.tips2 to authenticated;
drop policy if exists tips2_parties_read on public.tips2;
create policy tips2_parties_read on public.tips2 for select to authenticated
  using (tipper = (select auth.uid()) or recipient = (select auth.uid()));

-- New notification kinds (superset): a tip waiting for you to listen, and a tip you earned by listening.
alter table public.notifications drop constraint if exists notifications_kind_check;
alter table public.notifications add constraint notifications_kind_check check (kind in
  ('direct_bridge','friend_request','friend_accepted','message','answered','joined','pod_added','pod_clip','pod_message','reminder','tip','tip_waiting','tip_earned'));

create or replace function private.usd(c int) returns text language sql immutable set search_path = '' as $$
  select '$' || case when c % 100 = 0 then (c / 100)::text else trim(to_char(c / 100.0, 'FM999990.00')) end $$;

create or replace function private.tip2_notify(t public.tips2, p_kind text, p_title text) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if t.recipient is null or (t.tipper is not null and private.is_blocked(t.recipient, t.tipper)) then return; end if;
  insert into public.notifications (user_id, kind, actor, actor_name, bridge_id, group_pod_id, title)
  values (t.recipient, p_kind, t.tipper, left(t.tipper_name, 40),
          case when t.pod_kind = 'bridge' then t.pod_ref end,
          case when t.pod_kind = 'group_clip' then (select c.pod_id from public.group_pod_clips c where c.id = t.pod_ref) end,
          left(p_title, 300));
end $$;
revoke all on function private.tip2_notify(public.tips2, text, text) from public, anon, authenticated;

-- Has this person answered this clip? (bridge = duo pod answer; group_clip = answer on that clip)
create or replace function private.tip2_answered(p_kind text, p_ref uuid, p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select case p_kind
    when 'bridge' then exists (select 1 from public.answers a where a.bridge_id = p_ref and a.user_id = p_user)
    when 'group_clip' then exists (select 1 from public.group_pod_answers a where a.clip_id = p_ref and a.user_id = p_user)
    else false end $$;
revoke all on function private.tip2_answered(text, uuid, uuid) from public, anon, authenticated;

-- Is this person (still) a member of the pod the clip belongs to?
create or replace function private.tip2_member(p_kind text, p_ref uuid, p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select case p_kind
    when 'bridge' then exists (select 1 from public.bridge_members m where m.bridge_id = p_ref and m.user_id = p_user)
    when 'group_clip' then exists (select 1 from public.group_pod_clips c join public.group_pod_members m on m.pod_id = c.pod_id
                                   where c.id = p_ref and m.user_id = p_user)
    else false end $$;
revoke all on function private.tip2_member(text, uuid, uuid) from public, anon, authenticated;

-- Can the caller tip this person at all? (not self, not blocked; onboarding no longer required)
create or replace function public.tips2_can_tip(p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select (select auth.uid()) is not null and p_user is not null and p_user <> (select auth.uid())
     and not private.is_blocked((select auth.uid()), p_user)
     and exists (select 1 from public.profiles p where p.id = p_user)
$$;
revoke all on function public.tips2_can_tip(uuid) from public, anon;
grant execute on function public.tips2_can_tip(uuid) to authenticated;

-- Server-side checks for a new tip (service role only; tips2-checkout). Returns the destination account when the
-- recipient is ready AND it's a thank-you tip (listening tips are always held on the platform).
create or replace function public.tips2_prepare(p_tipper uuid, p_recipient uuid, p_purpose text, p_kind text, p_ref uuid)
returns table (stripe_account_id text, recipient_name text, tipper_name text, title text)
language plpgsql stable security definer set search_path = '' as $$
declare acct text; rn text; tn text; t text := '';
begin
  if p_tipper is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  if p_purpose not in ('thanks','listen') then raise exception 'Bad request' using errcode = '22023'; end if;
  if p_recipient is null or p_recipient = p_tipper then raise exception 'You can''t tip yourself' using errcode = 'P0001'; end if;
  select display_name into tn from public.profiles where id = p_tipper;
  if tn is null then raise exception 'Finish setting up your profile first' using errcode = 'P0001'; end if;
  select display_name into rn from public.profiles where id = p_recipient;
  if rn is null or private.is_blocked(p_tipper, p_recipient) then raise exception 'Person not found' using errcode = 'P0001'; end if;
  if p_kind is not null and p_kind not in ('bridge','group_clip') then raise exception 'Bad request' using errcode = '22023'; end if;
  if p_purpose = 'listen' and p_kind is null then raise exception 'Pick a clip to tip for' using errcode = 'P0001'; end if;
  if p_kind = 'bridge' then select b.clip_title into t from public.bridges b where b.id = p_ref;
  elsif p_kind = 'group_clip' then select c.title into t from public.group_pod_clips c where c.id = p_ref; end if;
  if p_kind is not null and (t is null or not private.tip2_member(p_kind, p_ref, p_tipper)) then raise exception 'Pod not found' using errcode = 'P0001'; end if;
  if p_purpose = 'thanks' and p_kind = 'bridge' and not exists (select 1 from public.bridges b where b.id = p_ref and b.created_by = p_recipient) then raise exception 'Pod not found' using errcode = 'P0001'; end if;
  if p_purpose = 'thanks' and p_kind = 'group_clip' and not exists (select 1 from public.group_pod_clips c where c.id = p_ref and c.shared_by = p_recipient) then raise exception 'Pod not found' using errcode = 'P0001'; end if;
  if p_purpose = 'listen' then
    if not private.tip2_member(p_kind, p_ref, p_recipient) then raise exception '% isn''t in this pod', rn using errcode = 'P0001'; end if;
    if private.tip2_answered(p_kind, p_ref, p_recipient) then raise exception '% already answered this one', rn using errcode = 'P0001'; end if;
  else
    select a.stripe_account_id into acct from public.tip_accounts2 a where a.user_id = p_recipient and a.payouts_enabled and a.charges_enabled;
  end if;
  return query select acct, rn, tn, coalesce(t, '');
end $$;
revoke all on function public.tips2_prepare(uuid, uuid, text, text, uuid) from public, anon, authenticated;
grant execute on function public.tips2_prepare(uuid, uuid, text, text, uuid) to service_role;

-- Webhook: a Checkout payment succeeded (idempotent). destination -> paid_out; thank-you on platform -> earned;
-- listening tip -> held (or earned right away if they already answered). Notifies the recipient.
create or replace function public.tips2_mark_paid(p_session text, p_payment_intent text, p_livemode boolean)
returns uuid language plpgsql security definer set search_path = '' as $$
declare t public.tips2; st text;
begin
  select * into t from public.tips2 where checkout_session_id = p_session and status = 'pending' for update;
  if t.id is null then return null; end if;
  st := case when t.mode = 'destination' then 'paid_out'
             when t.purpose = 'listen' and not private.tip2_answered(t.pod_kind, t.pod_ref, t.recipient) then 'held'
             else 'earned' end;
  update public.tips2 set status = st, paid_at = now(), payment_intent_id = coalesce(p_payment_intent, payment_intent_id),
         livemode = coalesce(p_livemode, livemode),
         earned_at = case when st in ('earned','paid_out') then now() end,
         paid_out_at = case when st = 'paid_out' then now() end
   where id = t.id returning * into t;
  if st = 'paid_out' then perform private.tip2_notify(t, 'tip', private.usd(t.amount_cents));
  elsif st = 'held' then perform private.tip2_notify(t, 'tip_waiting', private.usd(t.amount_cents) || ' tip for listening to “' || t.title || '”. Answer to earn it');
  elsif t.purpose = 'listen' then perform private.tip2_notify(t, 'tip_earned', private.usd(t.amount_cents) || ' for listening to “' || t.title || '”');
  else perform private.tip2_notify(t, 'tip', private.usd(t.amount_cents) || '. Set up payouts to collect it');
  end if;
  return t.id;
end $$;
revoke all on function public.tips2_mark_paid(text, text, boolean) from public, anon, authenticated;
grant execute on function public.tips2_mark_paid(text, text, boolean) to service_role;

-- Answering a clip earns any listening tips held for you on it.
create or replace function private.tg_tips2_earn() returns trigger
language plpgsql security definer set search_path = '' as $$
declare t public.tips2; k text := case when tg_table_name = 'answers' then 'bridge' else 'group_clip' end;
        r uuid := (to_jsonb(new) ->> case when tg_table_name = 'answers' then 'bridge_id' else 'clip_id' end)::uuid;
begin
  for t in update public.tips2 set status = 'earned', earned_at = now()
            where pod_kind = k and pod_ref = r and recipient = new.user_id and purpose = 'listen' and status = 'held' returning * loop
    perform private.tip2_notify(t, 'tip_earned', private.usd(t.amount_cents) || ' for listening to “' || t.title || '”');
  end loop;
  return null;
end $$;
revoke all on function private.tg_tips2_earn() from public, anon, authenticated;
drop trigger if exists tips2_earn on public.answers;
create trigger tips2_earn after insert on public.answers for each row execute function private.tg_tips2_earn();
drop trigger if exists tips2_earn on public.group_pod_answers;
create trigger tips2_earn after insert on public.group_pod_answers for each row execute function private.tg_tips2_earn();

-- For the sweep (service role): held tips that can no longer be earned (30 days, or pod/clip/membership gone),
-- and earned tips unclaimed for 90 days.
create or replace function public.tips2_refundable() returns setof public.tips2
language sql stable security definer set search_path = '' as $$
  select * from public.tips2 t where t.mode = 'platform' and t.payment_intent_id is not null and (
    (t.status = 'held' and (t.paid_at < now() - interval '30 days' or t.recipient is null
                            or not private.tip2_member(t.pod_kind, t.pod_ref, t.recipient)))
    or (t.status = 'earned' and (t.earned_at < now() - interval '90 days' or t.recipient is null)))
$$;
revoke all on function public.tips2_refundable() from public, anon, authenticated;
grant execute on function public.tips2_refundable() to service_role;

-- Admin: tips v2 totals by status (Smoke accounts excluded), incl. the held total.
create or replace function public.admin_tip_stats2() returns jsonb
language plpgsql stable security definer set search_path = public, auth as $$
declare r jsonb;
begin
  if not public.is_stats_admin() then raise exception 'not allowed' using errcode = '42501'; end if;
  with t as (select x.* from tips2 x where x.status not in ('pending','failed')
               and not exists (select 1 from profiles p where p.id in (x.tipper, x.recipient) and p.display_name ilike 'smoke%'))
  select jsonb_build_object(
      'tips', count(*) filter (where status <> 'refunded'),
      'tipped_cents', coalesce(sum(amount_cents) filter (where status <> 'refunded'), 0),
      'app_cut_cents', coalesce(sum(app_cut_cents) filter (where status <> 'refunded'), 0),
      'held_cents', coalesce(sum(amount_cents) filter (where status = 'held'), 0), 'held', count(*) filter (where status = 'held'),
      'owed_cents', coalesce(sum(recipient_cents) filter (where status in ('earned','paying')), 0),
      'paid_out_cents', coalesce(sum(recipient_cents) filter (where status = 'paid_out'), 0),
      'refunded_cents', coalesce(sum(amount_cents) filter (where status = 'refunded'), 0),
      'recipients_set_up', (select count(*) from tip_accounts2 where payouts_enabled))
    into r from t;
  return r;
end $$;
revoke all on function public.admin_tip_stats2() from public, anon;
grant execute on function public.admin_tip_stats2() to authenticated;
