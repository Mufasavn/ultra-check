# Ultra Check 2.10 — Windows

## Download and run

This repository is private. Sign in to an authorized GitHub account, choose **Code → Download ZIP**, extract the entire ZIP and run **Ultra-Check.exe**. Python and Node are not needed to run the EXE. The standalone Windows ZIP is also provided locally with the release.

## Upgrade from 2.9

Exit the old application using **Exit Ultra Check**, then run the new EXE. Existing data remains in **%LOCALAPPDATA%\UltraCheck** under the same Windows account. Saved advertisers/domains, CSV export, ten encrypted Apify key slots, run history and Google settings are retained. Do not delete this data directory. Older portable data migration still works: place the new EXE next to the old **UltraCheck-data** folder on its first launch. Credentials encrypted for another Windows account/computer must be entered again.

## Choose Google or Microsoft Bing

On Domain lookup, select **Advertising platform**. Existing Google Search/Text behavior is retained. Bing uses Microsoft's documented public Ad Library API directly, without Apify charges or Proxy-Cheap. Google provider settings and usage meters still apply to Google only. Saved names/domains are a shared local bookmark list; the selected platform determines which source is queried.

### Bing: Advertiser → Domain

Enter a legal advertiser name or numeric Microsoft advertiser ID, click **Find advertisers**, verify the profile, select it and click **Domain lookup**. Use **Load more profiles** / **Load more Bing ads** to continue. Each ad's details are read to obtain first/last dates. Destination URL hosts are preferred, with displayed URL hosts used when no destination is available.

### Bing: Domain → Advertiser

Enter a domain and click **Find advertisers**. Ultra Check searches Microsoft's ad-content index and verifies that the destination or displayed hostname matches the domain or its subdomains. Lookalike domains and mentions in titles/descriptions alone are excluded. Use **Continue loading advertisers** for more source pages. Results and CSV identify the platform. Ten displayed results per page remain available.

### Bing scope and accuracy

- Microsoft publishes eligible Bing impressions in the **EU/EEA**, regardless of advertiser location. “All EU/EEA countries” is not worldwide coverage.
- The public API does **not expose a Search placement/ad-type field**. This release retains records with title, description, a valid URL and no media asset JSON, labeled **text candidates / placement unverified**. It does not claim an exact Search/Text-only classification.
- The documented search is by advertiser or ad content, not an exhaustive destination-domain index. Domain results are verified candidates, **not a complete list or total advertiser count**.
- First/last eligible impression dates are in **UTC**, can lag 1–3 days and do not prove current campaign status. The separate live/today check is disabled for Bing. A source last-date of today can be marked observed today, without asserting live status.
- Public access has rate limits. Requests are spaced by at least five seconds and one source page is loaded per click. HTTP 403/429 pauses new requests for at least 60 seconds, respecting a longer Retry-After value. No IP switching, CAPTCHA bypass, automatic retry loop or paid fallback is used. Cached records remain accessible, including after restart; continuation tokens last seven days.
- Each list response is cached for one hour; ad details for 24 hours. **Refresh data** bypasses the cache. Original fetch times are retained; the displayed Bing fetch time refers to the oldest record in the latest page, not the full session.

Microsoft documentation: https://learn.microsoft.com/en-us/advertising/guides/ad-library-api?view=bingads-13

## Validation

105 Python tests passed, including the existing Google/storage/Apify/proxy tests and 21 Bing tests. TypeScript checking and the UI build passed. The final Windows EXE passed application restart persistence, ten key fields, saved/result CSV, Google regression UI, both Bing lookup directions, manual Bing continuation, UTC dates, EU/EEA filters, 10/10/3 result pagination, platform reset and mobile layout checks. UI search tests use explicit fixtures, not production result counts.

The final EXE also fetched a real Microsoft ad detail for waterdropfilter.com. A real domain search returned two matching ad records from two advertiser IDs; these are content-search results, not the domain's total advertisers. The final repeated domain check reused those cached records. No paid Apify runs were started. See **validation/release-2.10.json**, **validation/ui-checks-2.10.json** and **validation/bing-live-2.10.json**.

## Build from source

Windows x64 and Python 3.12: `python -m pip install -r requirements.txt`, then `python ultra_server.py`. Run tests: `python -m unittest discover -p "test_*.py"`. Backend/storage are Python; the UI is React/TypeScript. For UI edits: `npm install`, then `npm run build`. Package the Windows EXE: `python -m PyInstaller --noconfirm Ultra-Check.spec`.

No user API keys, proxy passwords, saved lists or runtime databases are included. Repository visibility must remain private; no public deployment is required.
