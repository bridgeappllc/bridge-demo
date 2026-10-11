# Bridge — App Store & Google Play checklist

Bridge LLC · Hawaii, USA · bridgeappllc@gmail.com
App id: `com.bridgeappllc.bridge` · Name: **Bridge** · Version 1.0 (build 1)
Code: branch `store-ready` of bridgeappllc/bridge-demo (`/mobile` = Capacitor 8 project)

Legend: ✅ done on `store-ready` · ⬜ needs Paul / an account · 🔶 decision or follow-up

---

## 0. What is already done (no accounts needed)

| Requirement | Status |
|---|---|
| In-app account deletion (Apple 5.1.1(v), Google Play account-deletion policy) | ✅ Settings → Delete account → type DELETE. Deletes auth user + all their data; shared bridges stay for the partner as "Deleted user". |
| Web page for deletion requests (Google requires a URL that works without the app) | ✅ `support.html#delete-account` (in-app steps + email request) |
| UGC safeguards (Apple 1.2): report user / library item / chat message, block, terms with zero tolerance, contact info | ✅ Reports go to an admin-only table; review via `private.reports_review` (see `docs/MODERATION.md`) |
| Privacy policy, Terms (EULA), Support pages | ✅ DRAFTS: `privacy.html`, `terms.html`, `support.html`. Linked from welcome, sign-up and Settings. |
| 13+ requirement | ✅ In the Terms and Privacy policy and on the sign-up line |
| App bundles its own web assets (Apple 4.2: not just a website wrapper) | ✅ index/legal pages, supabase-js and capacitor.js are inside the app. Only the API and Google Fonts load from the network. |
| Native touches | ✅ Splash screen, icons, cream status bar, Android back button, external links in in-app browser, `bridge://` deep links |
| Android debug build | ✅ `/workspace/bridge-mobile/bridge-debug.apk` (targetSdk 36, minSdk 24) |
| iOS compile proof | ⬜ Workflow ready at `mobile/ci/ios-build.yml` (macos-26, unsigned simulator build). Needs installing in `.github/workflows/`: the bot token lacks the `workflow` scope (see `mobile/ci/README.md`). |

---

## 1. Accounts (Paul)

### Apple Developer Program
⬜ $99/year. Enroll as an **Organization** so the seller name shows "Bridge LLC". What you need:
- A **D-U-N-S number** for Bridge LLC. It's free from Dun & Bradstreet through Apple's lookup tool, and can take about 1–2 weeks.
- A public website on the company's domain. The GitHub Pages URL may be questioned, so a custom domain is recommended.
- Authority to bind the LLC to contracts.
- An Apple Account with 2-factor authentication.

Alternative: enroll as an **Individual** (faster, but the seller shows "Paul Gurrieri"). This can be converted to an Organization later.

### Google Play Console
⬜ $25 one-time.
- **Organization** account:
  - Needs a D-U-N-S number plus organization verification.
  - Not subject to the 12-tester rule below.
- **Personal** account:
  - Faster.
  - New personal accounts must run a **closed test with at least 12 testers opted in for 14 continuous days** before they can apply for production access.
  - See section 9.

> Recommendation: get the D-U-N-S number first (one number covers both stores), then open **Organization** accounts in both. That skips Google's 12-tester/14-day gate.

### Other
- ⬜ App Store Connect → Agreements, Tax and Banking: required even for a free app (accept the Free Apps agreement).
- ⬜ Google Play → Payments profile and identity verification.
- 🔶 Custom domain (e.g. `bridgeapp.com`). Optional, but it simplifies universal links, the support URL, Apple's website requirement and the legal pages.

---

## 2. Signing

### Android
1. ⬜ Create an **upload keystore** on the box and keep it out of git:
   ```
   keytool -genkeypair -v -keystore bridge-upload.jks -alias upload -keyalg RSA -keysize 4096 -validity 10000
   ```
   Back up the keystore and its password in two safe places.
2. ⬜ Use **Play App Signing** (the default). Google holds the app signing key; you sign uploads with the upload key.
3. Add a `release` `signingConfig` that reads from `~/.gradle/gradle.properties` or env vars, then:
   ```
   cd mobile && npm run build:web && npx cap sync android
   cd android && ./gradlew bundleRelease
   ```
   This produces `app/build/outputs/bundle/release/app-release.aab`. Play needs an **AAB**, not an APK.
4. Bump `versionCode` (integer, +1 every upload) and `versionName` in `mobile/android/app/build.gradle`.

### iOS
1. ⬜ Set your **Team ID** in Xcode → App target → Signing & Capabilities, and turn on "Automatically manage signing". This creates the certificate and profiles.
2. ⬜ Register the bundle id `com.bridgeappllc.bridge` (Xcode does this automatically) and create the app record in App Store Connect.
3. Building and uploading needs a Mac with Xcode 26+, or CI:
   - Locally: Xcode → Product → Archive → Distribute → App Store Connect.
   - Via CI: add an App Store Connect API key (Issuer ID, Key ID, .p8) as GitHub secrets, then extend `ios-build.yml` with a signed `xcodebuild archive` + `-exportArchive` (or fastlane).
4. Bump `MARKETING_VERSION` / `CURRENT_PROJECT_VERSION` for each upload.

---

## 3. Deep links

Already working: the custom scheme `bridge://b/<code>` on both platforms, and `?b=` / `#b/` links when the app is launched with one.

For **verified https links**, so that `https://bridgeappllc.github.io/bridge-demo/?b=…` opens the app:

### Android App Links
✅ The intent-filter with `autoVerify` is already in `AndroidManifest.xml` (host `bridgeappllc.github.io`, pathPrefix `/bridge-demo`).

⬜ Host `https://bridgeappllc.github.io/.well-known/assetlinks.json`:
- This must be at the **domain root**, so it needs a new repo `bridgeappllc/bridgeappllc.github.io` with Pages, or a custom domain.
- Use the SHA-256 of the **Play App Signing** certificate (Play Console → App integrity), plus the upload key and debug cert if wanted.

Debug cert SHA-256, from the current debug APK:
`2C:94:B1:D0:10:61:ED:6A:09:DC:2A:B4:2B:E1:04:06:CB:7C:EC:DA:44:C9:2B:E8:66:C3:9B:54:64:B7:71:7B`

```json
[{"relation":["delegate_permission/common.handle_all_urls"],
  "target":{"namespace":"android_app","package_name":"com.bridgeappllc.bridge",
  "sha256_cert_fingerprints":["<PLAY APP SIGNING SHA-256>"]}}]
```

### iOS Universal Links
⬜ Needs the Apple Team ID:
- Add the **Associated Domains** capability with `applinks:bridgeappllc.github.io`.
- Host `https://bridgeappllc.github.io/.well-known/apple-app-site-association`: JSON with no extension, `appIDs: ["<TEAMID>.com.bridgeappllc.bridge"]` and `components: [{"/": "/bridge-demo/*"}]`.

🔶 Invite links in the app keep using the public web URL (`APP_URL` = the live site inside the app), so a friend without the app still gets the web version.

---

## 4. Push notifications (not built yet — what's needed)

**Accounts and services:**
- ⬜ **Firebase** project (free): add an Android app `com.bridgeappllc.bridge`, then download `google-services.json` into `mobile/android/app/`.
- ⬜ **APNs auth key** (.p8) from the Apple Developer account (Keys → Apple Push Notification service). Note its Key ID and the Team ID. Either upload it to Firebase (to send to iOS via FCM) or send to APNs directly.
- ⬜ Xcode: add the **Push Notifications** capability (+ Background Modes → Remote notifications if needed).

**Code:**
- `npm i @capacitor/push-notifications` in `/mobile`, then `npx cap sync`.
- Request permission at a sensible moment, e.g. after creating the first bridge (not on launch).
- Android 13+: the `POST_NOTIFICATIONS` runtime permission.
- A new **migration**: `device_tokens` table (user_id, token, platform, updated_at) with RLS "own rows only". It is removed automatically by the account-deletion cascade.
- A **Supabase Edge Function** (or database webhook) that sends via the FCM HTTP v1 API on a new message, friend request or partner answer. It uses a Firebase service-account key stored as an Edge Function **secret**, never in the app.
- Update the privacy policy, Data Safety and the nutrition label: "Device or other IDs" (push token) for App functionality.

---

## 5. Store listing text (draft)

**Name:** Bridge
**Subtitle (iOS, ≤30):** Listen together, then talk
**Short description (Play, ≤80):** Share something with a friend, answer 3 questions, and talk about where you differ.

**Promotional text (iOS, ≤170):**
Pick a song, video or article. You and a friend each answer three quick questions — then Bridge shows where you see it differently and gives you a place to talk.

**Description:**
> Bridge turns "did you see this?" into a real conversation.
>
> Pick something you both listened to, watched or read — a song, a podcast, a video, an article. You each answer three short questions on your own. Then Bridge reveals your answers side by side and highlights where you see it differently, so you have something real to talk about.
>
> • Start as a guest in seconds — no password. Save your account with your email any time.
> • Invite a friend with a link or a short code.
> • Keep a library of things you love and share it with friends (or keep it private).
> • Add friends by username and start a new bridge in one tap.
> • Chat inside each bridge.
> • You're in control: choose who sees your library, block or report anyone, and delete your account in Settings whenever you want.
>
> No ads. We don't sell your data.
> Bridge is for ages 13 and up.

**Keywords (iOS, ≤100 chars):** `friends,conversation,music,podcast,discuss,questions,share,listen,together,chat,debate,opinions`

**Category:** Social Networking (primary). 🔶 Lifestyle is a possible secondary.

**URLs:**
- Support: `https://bridgeappllc.github.io/bridge-demo/support.html`
- Privacy: `https://bridgeappllc.github.io/bridge-demo/privacy.html`
- Marketing: optional.

**Copyright:** © 2026 Bridge LLC
**Contact email:** bridgeappllc@gmail.com

⬜ Google also needs a contact phone number (optional) and a physical address for **organization** accounts; this is shown publicly for apps with in-app purchases. Not needed here.

---

## 6. Screenshots & graphics

### Apple
| Asset | Size (portrait) | Notes |
|---|---|---|
| iPhone 6.9" | 1320×2868 (or 1290×2796) | **Required.** 1–10 images. Apple scales these down for smaller iPhones. |
| iPhone 6.5" | 1284×2778 or 1242×2688 | Only needed if no 6.9" set is provided |
| iPad 13" | 2064×2752 (or 2048×2732) | **Required because the project currently supports iPad** (`TARGETED_DEVICE_FAMILY = 1,2`) |
| App icon | 1024×1024 PNG, no alpha | ✅ `mobile/resources/icon-only.png`. Xcode already has it. |

🔶 iPad decision: either take iPad screenshots (the app is a centered 720px column and works fine on iPad), or set the device family to iPhone only (`1`) to skip them. In that case the app still runs on iPads in compatibility mode.

### Google Play
| Asset | Size | Notes |
|---|---|---|
| App icon | 512×512 PNG (32-bit) | Export from `mobile/resources/icon-only.png` |
| Feature graphic | 1024×500 JPG/PNG, no alpha | **Required.** Terracotta cream background + Logo C + "Listen together, then talk". |
| Phone screenshots | 2–8 images, 9:16, e.g. 1080×1920 or 1440×2560 | Min 320px, max 3840px per side |
| 7"/10" tablet | optional | Only if you want the "designed for tablets" placement |

**Suggested shots** (same set for both stores; take them from the simulator/emulator or with a Playwright mobile viewport at 3× scale):
1. Welcome
2. Pick something to share
3. Answering the 3 questions
4. Side-by-side reveal ("where you differ")
5. Chat
6. Library
7. Friend profile
8. Settings showing privacy controls

Use realistic demo content, not real users' data.

---

## 7. Privacy answers

What Bridge actually collects:
- Display name
- Username and bio
- Email address (only if the user saves the account)
- Library items (title, kind, creator, link, note)
- Answers and chat messages
- Friends and blocks
- Reports
- Auth user id

There is no analytics SDK, no ads, no tracking, no location, no contacts and no photos. Data is stored in Supabase (us-west-1); emails are sent via Resend. The IP address is seen by Supabase, GitHub Pages and Google Fonts as part of normal requests.

### Apple — App Privacy ("nutrition label")
- **Data used to track you:** None. Answer "No" to tracking. Do not add an ATT prompt.
- **Data linked to you** (purpose for all of them: **App Functionality**):
  - Contact Info → **Name** (display name), **Email Address**
  - User Content → **Other User Content** (answers, library items, bios), plus **Customer Support** if you keep support emails. 🔶 Apple has no separate "Messages" type for in-app chat in all versions of the form; if "Emails or Text Messages" is shown, Apple treats in-app chat as Other User Content.
  - Identifiers → **User ID**
- **Not collected:** Health, Financial, Location, Contacts, Browsing/Search History, Purchases, Usage Data, Diagnostics, Sensitive Info.
- 🔶 If you add push later: Identifiers → **Device ID** (push token), App Functionality.
- **Privacy Policy URL:** the privacy.html above.
- **Export compliance:** `ITSAppUsesNonExemptEncryption = NO` is already in Info.plist (HTTPS only, exempt).

### Google Play — Data safety
- Does the app collect or share user data? **Yes, collects**. Shared with third parties: **No.** Service providers acting on your behalf don't count as "sharing".
- Encrypted in transit: **Yes** (HTTPS).
- Users can request deletion: **Yes**:
  - in-app: Settings → Delete account
  - web: `https://bridgeappllc.github.io/bridge-demo/support.html#delete-account`
  - Enter this URL in the **Delete account URL** field.
- **Data types** (all "Collected", not shared, purpose **App functionality** + **Account management**; processed ephemerally: no):
  - Personal info → **Name** (required), **Email address** (optional, only when the account is saved), **User IDs** (required)
  - Messages → **Other in-app messages** (bridge chat)
  - App activity → **Other user-generated content** (answers, library, bio)
- **Not collected:** location, financial, health, photos/videos, audio, files, calendar, contacts, web history, app info/performance, device IDs (until push is added).
- Also in App content:
  - Ads: **No**.
  - Target audience: **13+**. Select 13–15, 16–17 and 18+, **not** under 13. This keeps the app out of the Families policy.
  - News app: No.
  - Government app: No.
  - Financial features: None.
  - Health: No.
  - Login credentials for review: see section 10.

---

## 8. Age rating answers

The app has **user-generated content, chat between users, and user profiles**, with no restriction to known contacts: anyone with an invite link, or anyone who adds you by username, can message you in a bridge.

### Apple (App Store Connect age rating questionnaire, 2025+ version)
- Violence, sexual content, profanity, horror, drugs, gambling, contests, medical, alcohol and similar: **None** in app-provided content.
- **User-Generated Content:** **Yes**
- **Messaging and Chat:** **Yes**
- Unrestricted web access: **No**. External links open in the in-app browser only when the user taps them. 🔶 Answer "No" unless a reviewer disagrees; the app does not offer general browsing.
- Advertising: **No**
- Parental controls / age assurance: **No** (the age requirement is set in the Terms)
- **Expected result: 13+** (Apple's tiers are now 4+/9+/13+/16+/18+). That matches the Terms.

### Google (IARC questionnaire)
- Category: **Social / Communication**
- Violence, sexuality, language, controlled substances, gambling: **No**
- **Users can interact or exchange content:** **Yes**
- Shares the user's location with others: **No**
- Allows purchases of digital goods: **No**
- **Expected result:** ESRB **Teen**, PEGI **12**, plus the "Users Interact" descriptor.

---

## 9. Google's closed-test requirement (personal accounts only)

If Bridge is published from a **personal** Play account created after Nov 13 2023:
1. Upload the AAB to **Testing → Closed testing** and create a tester list (Google Group or emails).
2. Get **at least 12 testers** to opt in via the opt-in link and install the app. They must stay opted in for **14 consecutive days**.
3. Testers should actually use it. Google asks about engagement and the feedback you got when you apply.
4. Then **apply for production access** (Dashboard). Google asks about the test, the app and its readiness; review typically takes up to about 7 days.

Tips:
- Recruit 15–20 people to have a buffer (friends/family with Android phones and Gmail accounts).
- Run the test while you wait for Apple enrollment.

**Organization accounts are exempt.**

---

## 10. App Review notes & demo account

**Sign-in:** Bridge works without credentials. Tap **"Sign Up Free"**, then pick a name; this uses a guest account (Supabase anonymous sign-in). So the reviewer **does not need a login** for most features. State this explicitly in the review notes.

**Two-person flows:** a bridge needs a partner, so prepare these before submission:
1. Create a **"Bridge Review" demo profile** owned by Paul (e.g. username `bridgereview`) with a few public library items.
2. Create a bridge from that account, answer the 3 questions, and put its **invite link** in the review notes. The reviewer opens it, joins, answers, sees the reveal and can chat. Paul's account can reply during review.
3. Re-check that the link still works right before submitting. Each invite only accepts one partner, so create a fresh one per submission (and one per store).

**Email sign-in:** "I Have an Account" sends a one-time code by email, which a reviewer cannot receive. Say so in the notes and point them to guest mode.
🔶 If Apple insists on a full account, options are:
- (a) a dedicated mailbox Paul controls (e.g. a Gmail alias), with Paul relaying the code during the review window; or
- (b) later, add a reviewer-only password login. This is not recommended for v1.

Mind the hosted limit of **30 anonymous sign-ins per hour**. Reviewers won't hit it, but a mass test might.

**Suggested review note (paste and adjust):**
> Bridge lets two friends react to the same song/article/video by answering three questions, then compare answers and chat.
> No login needed: tap "Sign Up Free", enter any name — this creates a guest account.
> To test the two-person flow, open this invite: <INVITE LINK> (our demo user has already answered).
> Moderation (Guideline 1.2): every profile has Report and Block; every chat message from the other person has "Report"; friends' library items have "Report this item". Reports are reviewed by Bridge LLC within 24 hours; the Terms (Settings → About Bridge → Terms) have a zero-tolerance policy for objectionable content and abusive users.
> Account deletion (5.1.1(v)): Profile → Settings → Delete account → type DELETE.
> Contact: bridgeappllc@gmail.com

**Google Play:** give the same instructions under **App access**: "All functionality is available without special access", plus the invite link.

---

## 11. Apple guideline self-check & remaining work

### Must do before submitting
- ⬜ **Legal review** of privacy.html / terms.html / support.html, then remove the DRAFT banners. Regenerate with `/workspace/bridge-ops/gen_legal.py` or edit the files directly.
- ⬜ **Merge `store-ready` → main** after Paul approves the preview. The privacy/terms/support URLs must be live on the public site before submission.
- ⬜ **Moderation commitment:**
  - check `private.reports_review` at least daily
  - act on reports within 24 hours (remove content, ban users)
  - see `docs/MODERATION.md`
- 🔶 **Objectionable-content filtering (1.2).** Apple asks for "a method for filtering objectionable material". Today there is report + block + 24-hour review. Consider adding a small word-list filter on chat, bio and library notes (DB trigger or client-side warning) before the first submission to reduce review risk.
- ⬜ Take the screenshots (section 6) and create the feature graphic.
- ⬜ Release builds: signed AAB (Android) and archive (iOS); bump versions every upload.

### Good to do
- 🔶 Self-host the DM Sans / DM Serif Display fonts in the app bundle so the first launch looks right offline. Today they come from Google Fonts, with a system-font fallback.
- 🔶 Offline screen: show a friendly "You're offline" message if Supabase can't be reached.
- 🔶 Test on real devices: Android (install the debug APK via `adb install` or file sharing) and iPhone (TestFlight once the Apple account exists).
- 🔶 Supabase advisors: turn on leaked-password protection (it doesn't apply to magic codes, but clears the warning). The anonymous sign-in warnings are expected.
- 🔶 Universal links / App Links (section 3) and push (section 4) can follow in 1.1.

---

## 12. Build commands (reference)

```bash
# one-time on a new machine: Node 22+, JDK 21, Android SDK (platform 36, build-tools 36)
cd mobile
npm ci
npm run build:web        # copies ../index.html, legal pages, assets → www/, vendors JS
npx cap sync             # android + ios
npm run android:debug    # → android/app/build/outputs/apk/debug/app-debug.apk
npx @capacitor/assets generate --iconBackgroundColor '#F3EBDF' --splashBackgroundColor '#F3EBDF'   # after changing resources/
```

- iOS: open `mobile/ios/App/App.xcodeproj` in Xcode 26+ (Swift Package Manager, no CocoaPods).
- CI: `mobile/ci/ios-build.yml` (unsigned simulator build). Move it to `.github/workflows/` to enable it; see `mobile/ci/README.md`.
