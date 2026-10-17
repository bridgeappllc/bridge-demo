-- Tips v2 goes live (additive): the admin totals count real-money (livemode) tips only; sandbox tips are reported as a count.
create or replace function public.admin_tip_stats2() returns jsonb
language plpgsql stable security definer set search_path = public, auth as $$
declare r jsonb;
begin
  if not public.is_stats_admin() then raise exception 'not allowed' using errcode = '42501'; end if;
  with t as (select x.* from tips2 x where x.livemode and x.status not in ('pending','failed')
               and not exists (select 1 from profiles p where p.id in (x.tipper, x.recipient) and p.display_name ilike 'smoke%'))
  select jsonb_build_object(
      'tips', count(*) filter (where status <> 'refunded'),
      'tipped_cents', coalesce(sum(amount_cents) filter (where status <> 'refunded'), 0),
      'app_cut_cents', coalesce(sum(app_cut_cents) filter (where status <> 'refunded'), 0),
      'held_cents', coalesce(sum(amount_cents) filter (where status = 'held'), 0), 'held', count(*) filter (where status = 'held'),
      'owed_cents', coalesce(sum(recipient_cents) filter (where status in ('earned','paying')), 0),
      'paid_out_cents', coalesce(sum(recipient_cents) filter (where status = 'paid_out'), 0),
      'refunded_cents', coalesce(sum(amount_cents) filter (where status = 'refunded'), 0),
      'recipients_set_up', (select count(*) from tip_accounts2 where payouts_enabled and livemode),
      'sandbox_tips', (select count(*) from tips2 where not livemode and status not in ('pending','failed')))
    into r from t;
  return r;
end $$;
revoke all on function public.admin_tip_stats2() from public, anon;
grant execute on function public.admin_tip_stats2() to authenticated;
