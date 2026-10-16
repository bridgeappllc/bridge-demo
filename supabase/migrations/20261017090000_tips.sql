-- Tips via Stripe Connect (additive only; nothing existing is changed except widening the notification kind list).
-- Recipients onboard a Stripe Connect Express account; tippers pay through hosted Stripe Checkout as a destination
-- charge. All Stripe calls happen in the tips-* edge functions (service role); clients only read their own rows.

-- One Stripe connected account per person. Owner reads only; written by the service role (edge functions).
create table if not exists public.tip_accounts (
  user_id           uuid primary key references auth.users(id) on delete cascade,
  stripe_account_id text not null unique check (stripe_account_id ~ '^acct_[A-Za-z0-9]+$'),
  details_submitted boolean not null default false,
  charges_enabled   boolean not null default false,
  payouts_enabled   boolean not null default false,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
alter table public.tip_accounts enable row level security;
revoke all on public.tip_accounts from anon, authenticated;
grant select on public.tip_accounts to authenticated;
drop policy if exists tip_accounts_owner_reads on public.tip_accounts;
create policy tip_accounts_owner_reads on public.tip_accounts for select to authenticated using (user_id = (select auth.uid()));

-- Tips. pod_kind/pod_ref point at what was tipped for ('bridge' = duo pod id, 'group_clip' = group pod clip id), or null (profile tip).
create table if not exists public.tips (
  id                 uuid primary key default gen_random_uuid(),
  tipper             uuid references auth.users(id) on delete set null,
  recipient          uuid references auth.users(id) on delete set null,
  tipper_name        text not null default '' check (char_length(tipper_name) <= 40),
  pod_kind           text check (pod_kind in ('bridge','group_clip')),
  pod_ref            uuid,
  amount_cents       int not null check (amount_cents between 200 and 10000),   -- the tip itself
  fee_cents          int not null check (fee_cents >= 0),                        -- processing fee paid by the tipper
  total_cents        int not null check (total_cents = amount_cents + fee_cents),-- what the card is charged
  app_cut_cents      int not null check (app_cut_cents >= 0),                    -- Pod Club's 10%
  application_fee_cents int not null check (application_fee_cents >= 0),         -- app cut + processing fee (Stripe fee comes out of this)
  recipient_cents    int not null check (recipient_cents = total_cents - application_fee_cents), -- transferred to the recipient (90%)
  stripe_account_id  text not null,
  checkout_session_id text unique,
  payment_intent_id  text,
  status             text not null default 'pending' check (status in ('pending','paid','failed','refunded')),
  livemode           boolean not null default false,
  created_at         timestamptz not null default now(),
  paid_at            timestamptz
);
create index if not exists tips_recipient_idx on public.tips (recipient, created_at desc);
create index if not exists tips_tipper_idx on public.tips (tipper, created_at desc);
alter table public.tips enable row level security;
revoke all on public.tips from anon, authenticated;
grant select on public.tips to authenticated;
drop policy if exists tips_parties_read on public.tips;
create policy tips_parties_read on public.tips for select to authenticated
  using (tipper = (select auth.uid()) or recipient = (select auth.uid()));

-- Notification kind for "X tipped you $5" (superset of the existing list).
alter table public.notifications drop constraint if exists notifications_kind_check;
alter table public.notifications add constraint notifications_kind_check check (kind in
  ('direct_bridge','friend_request','friend_accepted','message','answered','joined','pod_added','pod_clip','pod_message','reminder','tip'));

-- Can the caller tip this person? Only a yes/no: never reveals the account id. False for self, blocks either way, or no payouts.
create or replace function public.tips_enabled_for(p_user uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select (select auth.uid()) is not null and p_user is not null and p_user <> (select auth.uid())
     and not private.is_blocked((select auth.uid()), p_user)
     and exists (select 1 from public.tip_accounts a where a.user_id = p_user and a.payouts_enabled and a.charges_enabled)
$$;
revoke all on function public.tips_enabled_for(uuid) from public, anon;
grant execute on function public.tips_enabled_for(uuid) to authenticated;

-- Server-side checks for a new tip (service role only, called by the tips-checkout edge function).
-- Returns the destination account + names, or raises a friendly error.
create or replace function public.tip_prepare(p_tipper uuid, p_recipient uuid, p_kind text, p_ref uuid)
returns table (stripe_account_id text, recipient_name text, tipper_name text, title text)
language plpgsql stable security definer set search_path = '' as $$
declare acct text; rn text; tn text; t text := '';
begin
  if p_tipper is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  if p_recipient is null or p_recipient = p_tipper then raise exception 'You can''t tip yourself' using errcode = 'P0001'; end if;
  select display_name into tn from public.profiles where id = p_tipper;
  if tn is null then raise exception 'Finish setting up your profile first' using errcode = 'P0001'; end if;
  select display_name into rn from public.profiles where id = p_recipient;
  if rn is null or private.is_blocked(p_tipper, p_recipient) then raise exception 'Person not found' using errcode = 'P0001'; end if;
  if p_kind = 'bridge' then
    select b.clip_title into t from public.bridges b where b.id = p_ref and b.created_by = p_recipient
      and exists (select 1 from public.bridge_members m where m.bridge_id = b.id and m.user_id = p_tipper);
    if t is null then raise exception 'Pod not found' using errcode = 'P0001'; end if;
  elsif p_kind = 'group_clip' then
    select c.title into t from public.group_pod_clips c where c.id = p_ref and c.shared_by = p_recipient
      and exists (select 1 from public.group_pod_members m where m.pod_id = c.pod_id and m.user_id = p_tipper);
    if t is null then raise exception 'Pod not found' using errcode = 'P0001'; end if;
  elsif p_kind is not null then raise exception 'Bad request' using errcode = '22023';
  end if;
  select a.stripe_account_id into acct from public.tip_accounts a where a.user_id = p_recipient and a.payouts_enabled and a.charges_enabled;
  if acct is null then raise exception '% hasn''t set up tips yet', rn using errcode = 'P0001'; end if;
  return query select acct, rn, tn, coalesce(t, '');
end $$;
revoke all on function public.tip_prepare(uuid, uuid, text, uuid) from public, anon, authenticated;
grant execute on function public.tip_prepare(uuid, uuid, text, uuid) to service_role;

-- Webhook: mark a tip paid (idempotent) and notify the recipient "X tipped you $5" (skipped if they've blocked each other).
create or replace function public.tip_mark_paid(p_session text, p_payment_intent text, p_livemode boolean)
returns uuid language plpgsql security definer set search_path = '' as $$
declare t public.tips;
begin
  update public.tips set status = 'paid', paid_at = now(), payment_intent_id = coalesce(p_payment_intent, payment_intent_id), livemode = coalesce(p_livemode, livemode)
    where checkout_session_id = p_session and status = 'pending' returning * into t;
  if t.id is null then return null; end if;   -- unknown or already processed
  if t.recipient is not null and not (t.tipper is not null and private.is_blocked(t.recipient, t.tipper)) then
    insert into public.notifications (user_id, kind, actor, actor_name, bridge_id, group_pod_id, title)
    values (t.recipient, 'tip', t.tipper, left(t.tipper_name, 40),
            case when t.pod_kind = 'bridge' then t.pod_ref end,
            case when t.pod_kind = 'group_clip' then (select c.pod_id from public.group_pod_clips c where c.id = t.pod_ref) end,
            '$' || case when t.amount_cents % 100 = 0 then (t.amount_cents / 100)::text else trim(to_char(t.amount_cents / 100.0, 'FM999990.00')) end);
  end if;
  return t.id;
end $$;
revoke all on function public.tip_mark_paid(text, text, boolean) from public, anon, authenticated;
grant execute on function public.tip_mark_paid(text, text, boolean) to service_role;

-- Admin: tip totals (paid only, test accounts excluded). Same admin list as admin_stats.
create or replace function public.admin_tip_stats() returns jsonb
language plpgsql stable security definer set search_path = public, auth as $$
declare r jsonb;
begin
  if not public.is_stats_admin() then raise exception 'not allowed' using errcode = '42501'; end if;
  with t as (select x.* from tips x where x.status = 'paid'
               and not exists (select 1 from profiles p where p.id in (x.tipper, x.recipient) and p.display_name ilike 'smoke%'))
  select jsonb_build_object('tips', count(*), 'tipped_cents', coalesce(sum(amount_cents), 0),
         'app_cut_cents', coalesce(sum(app_cut_cents), 0), 'recipients_cents', coalesce(sum(recipient_cents), 0),
         'recipients_set_up', (select count(*) from tip_accounts where payouts_enabled))
    into r from t;
  return r;
end $$;
revoke all on function public.admin_tip_stats() from public, anon;
grant execute on function public.admin_tip_stats() to authenticated;
