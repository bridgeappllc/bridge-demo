-- Who has answered each clip in a group pod (no answer content), for pod members only. Lets the pod page show
-- "hasn't answered yet · 💸 Add a tip for listening" even before you've answered yourself (answers stay hidden by RLS).
create or replace function public.group_pod_answered(p_pod uuid) returns table (clip_id uuid, user_id uuid)
language sql stable security definer set search_path = '' as $$
  select a.clip_id, a.user_id from public.group_pod_answers a join public.group_pod_clips c on c.id = a.clip_id
   where c.pod_id = p_pod and private.is_group_member(p_pod) $$;
revoke all on function public.group_pod_answered(uuid) from public, anon;
grant execute on function public.group_pod_answered(uuid) to authenticated;
