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

## Content filter (word list)

Added in `supabase/migrations/20261011180000_content_filter.sql`. It runs **in the database**, so it applies to every app version and to the API directly. The app keeps a copy of the list only to show the message instantly.

| Where | Hate terms / slurs (`category = 'hate'`) | General profanity (`category = 'profanity'`) |
|---|---|---|
| Display names (profile + bridge name), @usernames, bios | blocked | **blocked** |
| Chat messages, bridge answers, library titles / notes / creators | blocked | **masked**: first letter kept, the rest becomes `*` (e.g. `f***`) |

- A blocked save fails with `Please keep it respectful` (SQLSTATE 23514, `detail` = `content_filter:<field>`). The app shows the same text inline under the field.
- After a masked chat message the app also shows "Sent — some words were hidden with ***".
- Report notes are **not** filtered, so people can quote what they're reporting.

### How matching works
- **Normalisation:**
  - text is lowercased
  - `!` or `|` between letters counts as `i` (`sh!t`)
  - leetspeak is mapped: `0→o 1→i 3→e 4→a 5→s 7→t @→a $→s`
  - every other non-letter becomes a space
- **Whole words only.** This avoids the Scunthorpe problem: Scunthorpe, classic, assassin, cocktail, Essex, Dickens, shiitake and spicy are all fine.
- **Stretched letters** are matched (`fuuuck`).
- **`match` modes**, per term:
  - `word`: exactly the word.
  - `stem`: the word plus a common ending (`s es ed er ers ing in y ies z`).
  - `anywhere`: inside any word. Use only for terms that never appear inside innocent words; today only `fuck`.
- Multi-word phrases (e.g. `kill yourself`) are allowed for `hate` terms only (they're blocked, never masked).
- **Known gaps:**
  - spaced-out letters (`f u c k`)
  - accented or look-alike Unicode letters (`fück`, full-width)
  - self-censoring (`f*ck`) is left as typed
  - numbers-only hate codes
  - new slang

  Reports + block cover these.
- **False-positive check:** the built-in list was run against a 74,744-word English dictionary. The only hits are real profanity/slur words. "Fagin" and "retarding" were removed by making those terms `word`.

### Editing the list (Supabase dashboard)
Use **Table Editor → `moderation_terms`**, or the SQL editor. Changes apply immediately on the server; apps refresh their copy within 6 hours (or right away after any rejected save).

```sql
-- add a term (lowercase letters and single spaces only)
insert into public.moderation_terms (term, category, match, note) values ('newslur', 'hate', 'stem', 'added after report #123');
-- relax a term that causes false positives
update public.moderation_terms set match = 'word' where term = 'ass';
-- remove a term
delete from public.moderation_terms where term = 'piss';
-- test a phrase before/after a change
select private.mod_scan('your test text'), private.mod_mask('your test text');
```

- Before adding a `stem` term, check its endings aren't real words: `spic` → *spicy*, which is why `spic` is `word`.
- Prefer `word` for short terms.

### Existing content
Content saved **before** the filter is never rewritten, and it doesn't stop people from editing other fields. Only a new or changed value is checked. To review what older content would match:

```sql
select * from private.content_filter_existing_matches;   -- field, row id, verdict (hate/profanity), value
```

Handle any rows like reports: edit or delete them in the Table Editor if needed.
