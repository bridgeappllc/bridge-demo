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

## Link filter (adult sites and URL shorteners)

No one can share porn/adult links on Pod Club. The database checks every link before it is saved: pod clips (`bridges.clip_url`, including direct sends), group pod clips (`group_pod_clips.url`) and library items (`library_items.url`). A blocked link fails with **"That link can't be shared on Pod Club."** The app checks first (via `link_ok`) and shows that message under the link field. The database check is what actually enforces it, so it can't be bypassed. Pod clip titles and direct-send notes now also go through the word filter above: hate terms are blocked and profanity is masked.

Migration: `supabase/migrations/20261015090000_link_filter.sql`. Domain list: `supabase/seed/blocked_domains.sql`, regenerated with `python3 tests/gen_blocked_domains.py`.

### The lists (admin-only, Table Editor → schema `public`)
| Table | What it does | Seeded with |
|---|---|---|
| `blocked_domains` (`domain`, `category` adult/shortener/manual, `source`) | blocks that domain **and every subdomain** | 47,568 adult domains, plus 28 URL shorteners |
| `blocked_link_keywords` (`keyword`, `exceptions`) | blocks any host containing the word | 20 words (porn, xxx, hentai, nsfw, sex, camgirl, onlyfans, …). `sex` has exceptions (essex, sussex, middlesex, unisex, …) |
| `allowed_domains` (`domain`) | overrides both lists (fixes false positives) | empty |

To block a site, add a row to `blocked_domains` with category `manual`, for example `badsite.com`. To unblock one, add its domain to `allowed_domains`; don't delete it from the list, because a regenerate would put it back. Changes take effect immediately. Users can't read or edit these tables.

**Source and license:** [StevenBlack/hosts](https://github.com/StevenBlack/hosts), "porn-only" extension (`alternates/porn-only/hosts`, 76,798 entries, downloaded 14 Oct 2026). StevenBlack/hosts is MIT-licensed. The porn extension combines these sources:
- Clefspeare13/pornhosts (MIT)
- Sinfonietta/hostfiles (MIT)
- tiuxo/hosts (CC BY 4.0)
- brijrajparmar27/host-sources (CC BY 4.0)
- bigdargon/hostsVN (MIT)

This attribution satisfies CC BY. The list was lowercased and `www.` was stripped. Subdomains of domains already on the list were dropped, because the parent domain blocks them anyway. That leaves 47,568 domains. Mainstream sites were spot-checked: reddit, x/twitter, youtube, blogspot, tumblr and spotify are not on the list.

### How matching works
The URL's host is normalized: lowercased, scheme/user:password@/port/trailing dot removed, percent-encoding decoded, Unicode dots (。) mapped to `.`, leading `www.`/`www2.` stripped, and international names converted to punycode (`bücher.de` becomes `xn--bcher-kva.de`). The host and each parent domain (`a.b.example.com`, `b.example.com`, `example.com`) are then looked up in the lists, and the keywords are matched against the host.

### Limitations
- **Shorteners are blocked outright** (bit.ly, t.co, tinyurl, linktr.ee, …). The database can't follow redirects, so a short link could hide anything. Users should paste the full link instead.
- **Only the domain is checked, not the path.** An adult page on a mainstream site (a reddit NSFW subreddit, an X post) isn't caught. Reports and the report review cover that.
- Any blocklist is incomplete and new sites appear all the time. Rerun the generator now and then, and use `manual` rows for anything reported.
- Keywords can over-block (for example a domain containing "sex" that isn't on the exceptions list). Use `allowed_domains` to fix that.

### Existing content
Nothing already saved is deleted or changed. The filter only runs when a link is added or changed (editing a note on an old item still works). To list existing matches, run in the SQL editor:
```sql
select 'bridges' t, id, clip_url, private.link_block_reason(clip_url) from bridges where private.link_block_reason(clip_url) is not null
union all select 'library_items', id, url, private.link_block_reason(url) from library_items where private.link_block_reason(url) is not null
union all select 'group_pod_clips', id, url, private.link_block_reason(url) from group_pod_clips where private.link_block_reason(url) is not null;
```

## Profile photos

Added in `supabase/migrations/20261011200000_profile_photos.sql`.

### How photos are stored
- Photos live in the public Storage bucket **`avatars`** at `avatars/<user id>/<random>.webp` (or `.jpg`).
- The app crops each photo to a square and shrinks it to 512 px on the phone before uploading.
- **Server-side limits:**
  - 2 MB per file
  - JPEG / PNG / WebP only (bucket settings)
  - at most 3 files per person
  - people can only write in their own folder
- `profiles.avatar_url` holds the path plus `?v=<time>`. A check constraint means it can only point into the owner's own folder, and only at a file that exists.

### Who can see photos
- The public URL is unguessable, and nobody can list another person's folder.
- The app gets photo paths only from `avatars()` and `invite_avatar()`, which follow the same rules as names: signed in, and not across a block.
- Anyone who already has a URL can open it, like any public image link. Blocking someone stops the app showing them your photo, but it doesn't revoke a URL they already saw.

### Reviewing a reported photo
Reports with reason **`inappropriate_photo`** (target type `user`) keep the photo path in `snapshot` (`… — photo: avatars/<path>`).

To review one:
1. Open the photo in the dashboard: **Storage → avatars → `<user id>`**. Or open `https://gozjxubvvzxkkoxxvldo.supabase.co/storage/v1/object/public/avatars/<path without ?v=…>`.
2. To take a photo down:
   ```sql
   update public.profiles set avatar_url = null where id = '<user id>';   -- stop showing it
   ```
   Then delete the file in **Storage → avatars → `<user id>`** with the dashboard's Delete button. SQL can't delete Storage files: hosted Storage blocks `delete from storage.objects` so the stored bytes aren't orphaned.
3. Mark the report `actioned`, as for other reports.

If the person replaced their photo after the report, the old file is already gone. The report snapshot still shows its path.

### Account deletion and photos
In-app **Delete account** first deletes the person's photo files through the Storage API, then deletes the account. `delete_my_account()` refuses while any photo file remains, so no photo outlives an account deleted from the app.

If you delete a user from the **dashboard** (Authentication → Users), delete their `avatars/<user id>/` folder in Storage too.
