# Ultra Check 2.10.1 — Windows


## 2.10.1: Bing missing-results fix

The 2.10 Bing adapter incorrectly discarded title-only records with blank descriptions. It also fetched each ad's dates before returning the remaining list records; a detail rate limit could hide ads already available in the list response.

This update loads advertiser/domain lists first, including valid title-only text candidates. Date details load separately and never remove list records. Click **Load dates (up to 3 ads)** or **Load remaining dates**. Both stop on restrictions, retain successful results and reuse cached dates. Refresh data reloads lists and marks dates for explicit refresh. Dates from only some ads in a group are explicitly marked pending; they must not be treated as complete campaign bounds.

**Load all source pages** is enabled by default for Bing. Disable it to load one source page per click. Each source page contains up to 12 ads, matching the native library page size; the results table still shows 10 groups per page. Requests are spaced by at least **15 seconds**, with cancellation and persistent rate-limit cooldown. No paid fallback, proxy rotation or CAPTCHA bypass is used. Public Microsoft limits can still interrupt a scan.

The source progress panel distinguishes the Microsoft ad count, unique source records read, matching text records, media exclusions and other exclusions. Advertiser counts refer to unique IDs among domain-matched records, not the number of ads. A completed source query does not imply a complete global destination-domain index or verified Search/Text classification.

### meshy.ai audit — November 3, 2026

With All countries and November 3, 2025–November 3, 2026, the native Microsoft library and public API returned **85 ads over 8 pages**. All 85 unique source records were read. **80 text candidates matched meshy.ai and belonged to 2 advertiser IDs**: 4295387593 (79 ads) and 4294970211 (1 ad). Two records contained media assets and were excluded conservatively; three text records belonged to 4295383976 but pointed to tripo3d.ai, so they were not counted as meshy.ai advertisers. Seven valid text candidates had blank descriptions and are now included.

The final packaged EXE replayed those original public responses through its real cache and UI, confirming all counters, both advertisers and 80 retained ads without date requests. A separate one-ad live Microsoft detail request passed. Date-rate-limit UI tests retained all 80 ads and stopped automatic enrichment. The source fixture in fixtures/ preserves public IDs and field structure but removes ad copy and tracking URLs. It is test data, not a production cache.

**118 Python tests passed**, plus TypeScript checking, UI build, packaged Google/Bing regression checks, manual and automatic Bing pagination, date failure retention and the real-response audit. No paid Apify runs were created. One pre-existing proxy mock test failed transiently once; its isolated rerun and subsequent full 118-test run passed without proxy code changes.

See validation/release-2.10.1.json, validation/ui-checks-2.10.1.json and validation/bing-meshy-audit-2.10.1.json. The prior 2.10 validation files below describe that historical release, not the current build.

## Download and run

This repository is private. Sign in to an authorized GitHub account, choose **Code → Download ZIP**, extract the entire ZIP and run **Ultra-Check.exe**. Python and Node are not needed to run the EXE. The standalone Windows ZIP is also provided locally with the release.

## Upgrade from 2.9

Exit the old application using **Exit Ultra Check**, then run the new EXE. Existing data remains in **%LOCALAPPDATA%\UltraCheck** under the same Windows account. Saved advertisers/domains, CSV export, ten encrypted Apify key slots, run history and Google settings are retained. Do not delete this data directory. Older portable data migration still works: place the new EXE next to the old **UltraCheck-data** folder on its first launch. Credentials encrypted for another Windows account/computer must be entered again.

## Choose Google or Microsoft Bing

On Domain lookup, select **Advertising platform**. Existing Google Search/Text behavior is retained. Bing uses Microsoft's documented public Ad Library API directly, without Apify charges or Proxy-Cheap. Google provider settings and usage meters still apply to Google only. Saved names/domains are a shared local bookmark list; the selected platform determines which source is queried.

### Bing: Advertiser → Domain

Enter a legal advertiser name or numeric Microsoft advertiser ID, click **Find advertisers**, verify the profile, select it and click **Domain lookup**. Use **Load more profiles** / **Load more Bing ads** to continue. Date details are read separately on request, after list records are available. Destination URL hosts are preferred, with displayed URL hosts used when no destination is available.

### Bing: Domain → Advertiser

Enter a domain and click **Find advertisers**. Ultra Check searches Microsoft's ad-content index and verifies that the destination or displayed hostname matches the domain or its subdomains. Lookalike domains and mentions in titles/descriptions alone are excluded. Use **Continue loading advertisers** for more source pages. Results and CSV identify the platform. Ten displayed results per page remain available.

### Bing scope and accuracy

- Microsoft publishes eligible Bing impressions in the **EU/EEA**, regardless of advertiser location. “All EU/EEA countries” is not worldwide coverage.
- The public API does **not expose a Search placement/ad-type field**. This release retains records with a title or description, a valid URL and no media assets, labeled **text candidates / placement unverified**. It does not claim an exact Search/Text-only classification.
- The documented search is by advertiser or ad content, not an exhaustive destination-domain index. Domain results are verified candidates, **not a complete list or total advertiser count**.
- First/last eligible impression dates are in **UTC**, can lag 1–3 days and do not prove current campaign status. The separate live/today check is disabled for Bing. A source last-date of today can be marked observed today, without asserting live status.
- Public access has rate limits. Requests are spaced by at least 15 seconds. Load all source pages is enabled by default and can be disabled for manual continuation. HTTP 403/429 pauses new requests for at least 60 seconds, respecting a longer Retry-After value. No IP switching, CAPTCHA bypass, automatic retry loop or paid fallback is used. Cached records remain accessible, including after restart; continuation tokens last seven days.
- Each list response is cached for one hour; ad details for 24 hours. **Refresh data** bypasses the cache. Original fetch times are retained; the displayed Bing fetch time refers to the oldest record in the latest page, not the full session.

Microsoft documentation: https://learn.microsoft.com/en-us/advertising/guides/ad-library-api?view=bingads-13

## Historical 2.10 validation

105 Python tests passed, including the existing Google/storage/Apify/proxy tests and 21 Bing tests. TypeScript checking and the UI build passed. The final Windows EXE passed application restart persistence, ten key fields, saved/result CSV, Google regression UI, both Bing lookup directions, manual Bing continuation, UTC dates, EU/EEA filters, 10/10/3 result pagination, platform reset and mobile layout checks. UI search tests use explicit fixtures, not production result counts.

The final EXE also fetched a real Microsoft ad detail for waterdropfilter.com. A real domain search returned two matching ad records from two advertiser IDs; these are content-search results, not the domain's total advertisers. The final repeated domain check reused those cached records. No paid Apify runs were started. See **validation/release-2.10.json**, **validation/ui-checks-2.10.json** and **validation/bing-live-2.10.json**.

## Build from source

Windows x64 and Python 3.12: `python -m pip install -r requirements.txt`, then `python ultra_server.py`. Run tests: `python -m unittest discover -p "test_*.py"`. Backend/storage are Python; the UI is React/TypeScript. For UI edits: `npm install`, then `npm run build`. Package the Windows EXE: `python -m PyInstaller --noconfirm Ultra-Check.spec`.

No user API keys, proxy passwords, saved lists or runtime databases are included. Repository visibility must remain private; no public deployment is required.
