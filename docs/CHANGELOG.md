# Release 2.9

- Stable per-user Windows storage replaces dependence on the current EXE directory.
- Atomic saved lists, durable writes, last-known-good backup and one-time legacy migration.
- Combined CSV export for saved advertisers and domains.
- Ten API slots, preserving existing five-slot vaults and ordered account-aware failover.
- Removal of cost preflight from normal searches; configured per-run cap retained.
- English application labels, help, errors, progress and CSV headings; source ad content remains unchanged.
- Existing 2.8 Apify run history and optional Proxy-Cheap features retained.

This repository is a private source/archive upload of Ultra Check 2.9, not a public publication or deployment.


## 2.10 — 2026-11-03

Added Google/Bing platform selection, the public Microsoft API adapter, advertiser discovery, verified candidate domain lookup, reported UTC dates, EU/EEA country filters, manual source pagination, platform-labelled CSV and explicit coverage/type limitations. Existing Google providers, storage, ten keys and history retained. 105 tests and packaged UI checks passed.


## 2.10.1 update



The 2.10 Bing adapter incorrectly discarded title-only records with blank descriptions. It also fetched each ad's dates before returning the remaining list records; a detail rate limit could hide ads already available in the list response.

This update loads advertiser/domain lists first, including valid title-only text candidates. Date details load separately and never remove list records. Click **Load dates (up to 3 ads)** or **Load remaining dates**. Both stop on restrictions, retain successful results and reuse cached dates. Refresh data reloads lists and marks dates for explicit refresh. Dates from only some ads in a group are explicitly marked pending; they must not be treated as complete campaign bounds.

**Load all source pages** is enabled by default for Bing. Disable it to load one source page per click. Each source page contains up to 12 ads, matching the native library page size; the results table still shows 10 groups per page. Requests are spaced by at least **15 seconds**, with cancellation and persistent rate-limit cooldown. No paid fallback, proxy rotation or CAPTCHA bypass is used. Public Microsoft limits can still interrupt a scan.

The source progress panel distinguishes the Microsoft ad count, unique source records read, matching text records, media exclusions and other exclusions. Advertiser counts refer to unique IDs among domain-matched records, not the number of ads. A completed source query does not imply a complete global destination-domain index or verified Search/Text classification.

