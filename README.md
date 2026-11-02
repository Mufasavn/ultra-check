# Ultra Check Windows 2.9

## Upgrade and keep your lists

1. Exit the previous application using **Exit Ultra Check**.
2. Place the new Ultra-Check.exe next to the OLD UltraCheck-data folder for its first launch. Do not delete the old folder.
3. Start the new EXE. Existing saved lists, API vault, proxy settings and the main run/cache database are migrated without deleting the old files.
4. From this release onward, data is stored at **%LOCALAPPDATA%/UltraCheck**, under your current Windows account. Moving or replacing the EXE no longer changes where your saved lists are stored. Rebooting does not clear them. The exact location is shown on Saved lists.

Only data still available in the old folder can be recovered. If an older ZIP was extracted into a different folder, find its UltraCheck-data and place the new EXE next to it for the first launch. The program does not scan the entire computer. Existing stable lists are merged, not replaced; migration from each old folder is performed once so removed items do not reappear on every launch. Keep a backup before removing any old folder.

Lists are written atomically and flushed to disk, with a last-known-good saved.json.bak backup. API credentials remain encrypted to your Windows account. Moving to a different computer or Windows account requires entering credentials again.

## Saved lists and CSV

Open **Saved lists**. Both advertiser names and domains remain available after a restart. Click **Export saved CSV** to export both lists into one UTF-8 CSV with Type and Name or domain columns. Values that could be interpreted as spreadsheet formulas are escaped. Saved advertiser names, domain names and ad content are not translated or changed.

## Ten Apify API slots

Open **Apify API**. There are now 10 encrypted API slots. Existing five-slot vaults are upgraded automatically without dropping keys. When an account is conclusively out of quota/balance before a new run is accepted, the application tries the next available slot in order. Keys from the same Apify account share one quota and do not multiply the account allowance. After a run ID is accepted, network errors do not create another run on a different key. Usage percentages remain account-level snapshots.

## No cost preflight

The cost-check option, overview preflight and confirmation dialog have been removed from normal searches. An uncached search starts using the USD limit configured in **Data source**. This is a per-Actor-run limit, not a free scan or a total session budget. A domain search may have separate historical and today runs. The application does not increase the budget automatically. Results remain explicitly incomplete if a source or cost limit is reached. A cached partial result is reused; select **Refresh data (skip cache)** when you deliberately want a new run, which may charge for old ads again.

## English interface

Navigation, settings, status messages, source errors, CSV headings and help are in English. No translation service is used at runtime. Advertiser names and original source content remain unchanged for accuracy.

## Existing features

Both lookup directions, date/country filters, Search/Text scope, 10 results per page, CSV result export, today checks, optional Proxy-Cheap, usage estimates, local caching and persistent Apify run history remain available. Proxy usage is a local HTTP-payload estimate plus your manual baseline, not synchronized provider billing. Google restrictions/CAPTCHA stop the session; no IP switching or automatic paid fallback is performed.

## Validation

84 Python tests passed, including stable storage across different EXE locations, backup recovery, migration of an old five-slot vault, failover through the tenth key, and search without cost preflight. The packaged EXE was checked for bookmark retention after shutdown/restart, combined saved-list CSV content, 10 API fields, English screens, mobile layout, and 23 fixture results paginated 10/10/3. Test-only data directories were used; no paid Apify runs were created. The CSV contents were checked rather than an interactive Save dialog. See UI-checks.json and Test-summary.json.

## Build from source

Windows x64, Python 3.12: `python -m pip install -r requirements.txt`, then `python ultra_server.py`. Run tests with `python -m unittest discover -p "test_*.py"`. If editing the React UI, run `npm install` and `npm run build`. Package with `python -m PyInstaller --noconfirm Ultra-Check.spec`. Backend and storage are Python; the UI is React/TypeScript.
