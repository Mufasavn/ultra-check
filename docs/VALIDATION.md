# Validation

The original 2.9 release reported 84 passing Python tests and the executable checks recorded in `validation/`. Its EXE SHA-256 is included there.

The UI checks use isolated data and simulated search/API responses. They cover saved-list restart persistence, backup creation, combined saved CSV contents, ten API fields, no preflight modal, 23 results paginated 10/10/3, English UI, mobile layout and no browser runtime errors. CSV content was checked, not an interactive Save dialog. No paid Actor run was created by those UI checks.

Unit coverage includes stable storage when the EXE folder changes, migration of the five-slot vault, failover through slot ten, backup recovery, cache behavior, run-history persistence, source/filter validation and bounded proxy error handling.

Run on Windows with Python 3.12 after installing requirements:

```powershell
python -m unittest discover -p "test_*.py"
```

No real credentials or personal datasets are required for unit tests. Original benchmark datasets and personal runtime folders are excluded.


## Release 2.10

105 Python tests, TypeScript checking and bundled UI build passed. Packaged UI checks cover both platforms, both Bing directions, manual continuation, 10/10/3 fixture pagination, source isolation, UTC dates, country labels/filters, CSV scope, restart persistence, 10 key slots and mobile overflow. One final live Microsoft detail request and cached replay of two real domain-query records passed; no paid Apify runs were started. These checks do not certify exhaustive Bing coverage or Search/Text placement. See validation/*2.10.json.


## 2.10.1 update



The 2.10 Bing adapter incorrectly discarded title-only records with blank descriptions. It also fetched each ad's dates before returning the remaining list records; a detail rate limit could hide ads already available in the list response.

This update loads advertiser/domain lists first, including valid title-only text candidates. Date details load separately and never remove list records. Click **Load dates (up to 3 ads)** or **Load remaining dates**. Both stop on restrictions, retain successful results and reuse cached dates. Refresh data reloads lists and marks dates for explicit refresh. Dates from only some ads in a group are explicitly marked pending; they must not be treated as complete campaign bounds.

**Load all source pages** is enabled by default for Bing. Disable it to load one source page per click. Each source page contains up to 12 ads, matching the native library page size; the results table still shows 10 groups per page. Requests are spaced by at least **15 seconds**, with cancellation and persistent rate-limit cooldown. No paid fallback, proxy rotation or CAPTCHA bypass is used. Public Microsoft limits can still interrupt a scan.

The source progress panel distinguishes the Microsoft ad count, unique source records read, matching text records, media exclusions and other exclusions. Advertiser counts refer to unique IDs among domain-matched records, not the number of ads. A completed source query does not imply a complete global destination-domain index or verified Search/Text classification.

