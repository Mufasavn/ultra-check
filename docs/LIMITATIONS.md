# Data semantics and limitations

- Results are scoped to Google Search / Text, selected country and date filters. Exhausting source pages does not prove Google exposes every possible record.
- Green dots mean the source returned a record for today in US Pacific time, not a live campaign-enable signal.
- First/last observed dates belong to downloaded creatives; they are not campaign start/end dates.
- Displayed domains and OCR-derived domains may differ from final destinations after redirects. OCR needs verification; missing domains are not guessed.
- A source, sample or cost limit is reported as incomplete. Counts from incomplete data are lower bounds rather than definitive totals.
- Proxy usage is a local payload estimate plus a manual baseline, not provider billing. Headers/TLS and other account traffic are not fully included.
- Multiple API keys for one Apify account share that account's quota. Ten slots do not create ten separate balances unless they belong to independent eligible accounts.
- Run history preserves IDs, not remote dataset retention. Import needs an account with access to a still-available compatible Apify run.
- Windows DPAPI vaults are tied to the Windows user/machine. They are not credentials portable to another computer.
- No server-side user login, public hosting, GitHub Pages or deployment is configured in this repository.


## Bing 2.10

Microsoft Ad Library covers eligible EU/EEA impressions only. Public API search indexes advertiser names/ad content; destination-domain discovery is not guaranteed exhaustive. No placement or ad-type field is exposed, so text-shaped records are labeled candidates and are not certified Search/Text-only. Media assets are excluded conservatively. Dates are UTC and may lag 1–3 days; no live campaign status is claimed. Detail requests can take longer and hit stricter unauthenticated limits; all downloaded results are retained and continuation is manual. Displayed hostname matching is distinguished from destination hostname matching.


## 2.10.1 update



The 2.10 Bing adapter incorrectly discarded title-only records with blank descriptions. It also fetched each ad's dates before returning the remaining list records; a detail rate limit could hide ads already available in the list response.

This update loads advertiser/domain lists first, including valid title-only text candidates. Date details load separately and never remove list records. Click **Load dates (up to 3 ads)** or **Load remaining dates**. Both stop on restrictions, retain successful results and reuse cached dates. Refresh data reloads lists and marks dates for explicit refresh. Dates from only some ads in a group are explicitly marked pending; they must not be treated as complete campaign bounds.

**Load all source pages** is enabled by default for Bing. Disable it to load one source page per click. Each source page contains up to 12 ads, matching the native library page size; the results table still shows 10 groups per page. Requests are spaced by at least **15 seconds**, with cancellation and persistent rate-limit cooldown. No paid fallback, proxy rotation or CAPTCHA bypass is used. Public Microsoft limits can still interrupt a scan.

The source progress panel distinguishes the Microsoft ad count, unique source records read, matching text records, media exclusions and other exclusions. Advertiser counts refer to unique IDs among domain-matched records, not the number of ads. A completed source query does not imply a complete global destination-domain index or verified Search/Text classification.

