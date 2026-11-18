# Release 2.9.1

- Apify slots now keep the real reason a key cannot be used: a key rejected by Apify (HTTP 401/403, e.g. user-or-token-not-found) is shown as "Invalid key" with what to do, separate from network errors and empty quota. The "no usable key" error lists how many keys fall in each case.

- Password login: a password is required every time Ultra Check starts. First launch asks you to create one.
- Password stored only as a salted PBKDF2-SHA256 hash (auth.json in the data folder). Sessions are in memory and end when the app closes.
- Every API route and action (including Stop/Exit) requires a logged-in session; the page token and Host/Origin checks remain.
- Wrong passwords: after 5 failures, a wait of 30 s that doubles each further failure (max 15 min).
- Lock and Change password buttons in the footer. Changing the password ends other sessions.
- Self-test covers the login flow; live Google lookups in the self-test run only with ULTRA_LIVE_TEST=1.

# Release 2.9

- Stable per-user Windows storage replaces dependence on the current EXE directory.
- Atomic saved lists, durable writes, last-known-good backup and one-time legacy migration.
- Combined CSV export for saved advertisers and domains.
- Ten API slots, preserving existing five-slot vaults and ordered account-aware failover.
- Removal of cost preflight from normal searches; configured per-run cap retained.
- English application labels, help, errors, progress and CSV headings; source ad content remains unchanged.
- Existing 2.8 Apify run history and optional Proxy-Cheap features retained.

This repository is a private source/archive upload of Ultra Check 2.9, not a public publication or deployment.

# Release 2.9.2

- Ultra Check Bridge browser extension (bundled in the EXE and unpacked to the data folder): Google lookups run in the user's own browser tab; request token capture and cookie-less fallback for signed-in sessions.
- Midnight dark interface; intro banner and footer credits removed; connection label "GG extension".
- Progress bar with percentage for every search; failed searches are reported as stopped.
- dd/mm/yyyy dates with First seen / Last seen labels.
- Temporary page failures are retried up to two times so all source pages load.
- Based on 2.9.1 (password login). The Bing adapter from 2.10.x is not part of this line.

# Release 2.9.3

- Ad format selection (all / text / image / video) for both lookup directions; format filters, badges and CSV column.
- Advertiser -> Domain: candidate domains from ad previews verified with Google's advertiser + domain filter; second pass and end-of-scan matching; bounded paging of large lists; advertiser's only verified domain (labelled) for ads that show none; refuted display domains are not used.
- Preview downloads through the extension (1.3.0); extension reloads or replaces sleeping Google tabs (1.2.0).
- No limit on the number of selected advertiser profiles; Select all.
- LED dot-matrix pixel logo.
- Tests: 137.
