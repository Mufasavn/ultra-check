# Architecture — Ultra Check 2.9

Ultra Check is a Windows desktop application packaged as one executable. A Python HTTP server binds only to 127.0.0.1 on a dynamically selected port and serves the bundled React/TypeScript interface in the default browser.

## Code map

- `ultra_server.py`: local routes, source selection, request authentication, operation lock, cancellation and shutdown.
- `ultra_client.py`: Google public transparency RPC, Search/Text filters, source pagination, SQLite cache, display-domain extraction and Windows OCR.
- `apify_client.py`: pinned solidfetch Actor adapter, per-run USD cap, accepted-run polling, dataset paging, result normalization and import of existing runs.
- `apify_keys.py` / `key_vault.py`: 10 encrypted API slots; Windows DPAPI; account-level quota snapshots and conservative failover before a run is accepted.
- `proxy_client.py`: optional HTTP proxy, sticky-session suffix, bounded retries and persistent local HTTP-payload meter.
- `saved_store.py` / `data_store.py`: atomic saved lists, fsync, backup recovery, stable Windows profile directory and non-destructive portable-folder migration.
- `run_history.py`: persistent Apify run IDs and query metadata, including IDs saved immediately after acceptance and migration of old cached runs.
- `ui.tsx`, `assets/`, `ultra-core.mjs`: English interface, 10-row display pagination, status grouping and CSV export.

## Storage

Default: `%LOCALAPPDATA%/UltraCheck`. `--data-dir` explicitly overrides it for tests or controlled portable use. On first migration, old `UltraCheck-data` folders beside the EXE/current directory are examined; saved lists are merged and existing stable files are preserved. The program does not scan the whole computer. Preserve old data folders until migration is verified.

Main files include `saved.json` plus backup, encrypted API/proxy vaults, `cache.sqlite` and a separate proxy cache. Personal data files are intentionally excluded from this repository.

## Local request protection

The server validates Host, Origin where present and a per-session token on modifying requests. Only allowlisted source hosts are requested. Google verification or access restrictions stop the scan; no CAPTCHA bypass or automatic IP changes are used to continue a blocked session.

## Cost behavior

Normal searches do not run cost preflight or open a budget-confirmation dialog in 2.9. The configured per-Actor USD cap still applies. Historical and today lookups may create separate paid runs. Existing complete or partial caches can be reused; Refresh data explicitly requests new data. The program does not switch accounts after a run has already been accepted.


## 2.10: Bing adapter

`bing_client.py` implements the documented public Microsoft Ad Library API. Search POST bodies select `platform: "bing"`; missing platform remains Google for backward compatibility. Bing routes before all Apify/proxy processing and shares the existing SQLite cache, cancellation event and operation lock with separate cache keys. `/api/bing` supplies the supported EU/EEA countries and scope metadata. Domain lookup validates source URL hosts, with no requests to advertiser destinations. Text shape is a conservative candidate heuristic; placement/type is unverified. Continuation state and rate-limit cooldown persist in the main cache.


## 2.10.1 update



The 2.10 Bing adapter incorrectly discarded title-only records with blank descriptions. It also fetched each ad's dates before returning the remaining list records; a detail rate limit could hide ads already available in the list response.

This update loads advertiser/domain lists first, including valid title-only text candidates. Date details load separately and never remove list records. Click **Load dates (up to 3 ads)** or **Load remaining dates**. Both stop on restrictions, retain successful results and reuse cached dates. Refresh data reloads lists and marks dates for explicit refresh. Dates from only some ads in a group are explicitly marked pending; they must not be treated as complete campaign bounds.

**Load all source pages** is enabled by default for Bing. Disable it to load one source page per click. Each source page contains up to 12 ads, matching the native library page size; the results table still shows 10 groups per page. Requests are spaced by at least **15 seconds**, with cancellation and persistent rate-limit cooldown. No paid fallback, proxy rotation or CAPTCHA bypass is used. Public Microsoft limits can still interrupt a scan.

The source progress panel distinguishes the Microsoft ad count, unique source records read, matching text records, media exclusions and other exclusions. Advertiser counts refer to unique IDs among domain-matched records, not the number of ads. A completed source query does not imply a complete global destination-domain index or verified Search/Text classification.

