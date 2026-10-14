-- One question + 0–10 value rating (additive, safe on live).
-- New-style answers fill a3 (the takeaway question) + rating; a1/a2 become optional so old 3-answer rows (and the
-- currently live app, which still sends a1..a3 without a rating) keep working. A row must have either the old a1
-- or the new rating, so a new-style answer can't be submitted without its rating.
alter table public.answers add column if not exists rating smallint check (rating between 0 and 10);
alter table public.answers alter column a1 drop not null, alter column a2 drop not null;
alter table public.answers drop constraint if exists answers_a1_or_rating;
alter table public.answers add constraint answers_a1_or_rating check (a1 is not null or rating is not null);
grant insert (rating) on public.answers to authenticated;

alter table public.group_pod_answers add column if not exists rating smallint check (rating between 0 and 10);
alter table public.group_pod_answers alter column a1 drop not null, alter column a2 drop not null;
alter table public.group_pod_answers drop constraint if exists group_pod_answers_a1_or_rating;
alter table public.group_pod_answers add constraint group_pod_answers_a1_or_rating check (a1 is not null or rating is not null);

create or replace function private.answer_group_clip_v2(p_clip uuid, p_answer text, p_rating int) returns void
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid();
begin
  if me is null then raise exception 'Not signed in' using errcode = '28000'; end if;
  if not private.is_group_member(private.group_pod_of_clip(p_clip)) then raise exception 'Clip not found' using errcode = 'P0002'; end if;
  if p_rating is null or p_rating not between 0 and 10 then raise exception 'Pick a rating from 0 to 10' using errcode = '22023'; end if;
  if char_length(btrim(coalesce(p_answer, ''))) = 0 then raise exception 'Answer the question' using errcode = '22023'; end if;
  if private.group_clip_answered(p_clip) then raise exception 'You already answered this clip' using errcode = 'P0001'; end if;
  insert into public.group_pod_answers (clip_id, user_id, a3, rating) values (p_clip, me, btrim(p_answer), p_rating);
end $$;
create or replace function public.answer_group_clip_v2(p_clip uuid, p_answer text, p_rating int) returns void
language sql security invoker set search_path = '' as $$ select private.answer_group_clip_v2(p_clip, p_answer, p_rating) $$;
revoke all on function private.answer_group_clip_v2(uuid, text, int) from public, anon;
grant execute on function private.answer_group_clip_v2(uuid, text, int) to authenticated;
revoke all on function public.answer_group_clip_v2(uuid, text, int) from public, anon;
grant execute on function public.answer_group_clip_v2(uuid, text, int) to authenticated;
