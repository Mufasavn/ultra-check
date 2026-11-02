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
