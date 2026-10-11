# Moderation: reviewing reports (for Paul)

People can report a **person**, a **library item** or a **chat message** in the app (reason + optional note), and block anyone.
Reports go into `public.reports`. App users can't read, change or delete that table; only you can, as project owner.
Each report keeps a **snapshot** of what was reported, so you can still see it if the content is deleted later.

App Store and Google Play expect you to **act on reports within 24 hours** (the Terms promise this).

## See open reports
Supabase dashboard → project **bridge** → **SQL Editor** → run:

```sql
select * from private.reports_review where status = 'open';
```

Columns: `created_at`, `target_type` (user / library_item / message), `reason`, `note`, `snapshot` (the reported text),
`target_name`/`target_username`/`target_user` (who it's about), `reporter_name`, `reports_against_target` (total reports about that person).

## Act on a report
```sql
-- remove a reported chat message (target_id is the message id)
delete from public.messages where id = <target_id>;
-- remove a reported library item (target_id is the item id)
delete from public.library_items where id = '<target_id>';
-- remove an abusive user and all their data (same as them deleting their account)
delete from auth.users where id = '<target_user>';
-- mark the report handled (status: reviewed | actioned | dismissed)
update public.reports set status = 'actioned', reviewed_at = now(), admin_note = 'removed message' where id = <report id>;
```

Tip: to get a daily nudge, set a calendar reminder. An optional extra is a Database Webhook on `public.reports` inserts → an email to bridgeappllc@gmail.com.

## Account deletion (what happens)
`delete_my_account()` (Settings → Delete account) deletes the auth user. Cascades remove their profile, email, library, friendships/requests, blocks,
bridge memberships, answers, ratings and messages. Bridges only they were on are deleted. Shared bridges stay for the partner, closed
(`bridges.partner_left_at`) and shown as "Deleted user", and nobody can join them through the old invite link. Reports they filed are kept with
the reporter removed. Deleting a user from the dashboard (Authentication → Users) has the same effect.
