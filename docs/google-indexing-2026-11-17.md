# Google indexing investigation — 2026-11-17

## Evidence

The owner's GSC screenshots show six indexed URLs and exclusions of 1,152
`noindex`, ten 404, eight alternate canonical, two 5xx, 52 discovered but not
indexed, and 24 crawled but not indexed URLs.

The supplied `poslovi.aneskurtovic.com-Coverage-Drilldown-2026-11-17.zip`
contains the **noindex** drilldown, not the other exclusion groups. Its chart
covers November 6–13; its URL table contains 1,000 examples, fewer than the
1,152 in the report. Of those examples:

- 992 are `/report/` or `/en/report/` URLs, predominantly recursively nested
  `page` parameters, with repeated percent encoding.
- Seven are organization pages without jobs.
- One is `/?sort=deadline`.

The footer appended the entire current URL to the report link, including on
report pages themselves. Language alternates retained this query as well.
Following these links repeatedly created unbounded URL variants. A local
regression test reproduced this behavior before the fix. This explains the
exported report variants; it does **not** establish why Google has indexed
only six URLs or explain exclusions absent from the export.

## Owner's indexing policy and implementation

All public content should be eligible for indexing, including previous jobs.

- Published jobs remain indexable after expiry. Closed jobs with a publication
  timestamp remain readable with HTTP 200, unless manually rejected or marked
  duplicate. Public archive imports already carry publication timestamps.
- Archived pages retain the existing closed-vacancy notice and omit active
  `JobPosting` structured data. The active board and feed still show only
  current jobs.
- The sitemap includes all public jobs, every organization, the board, source
  coverage, report and privacy pages, in both Bosnian and English.
- Employer history titles link to the archived detail pages.
- Public organization pages, filtered/sorted listings and report pages no
  longer emit `noindex`. Filter/sort copies retain their canonical to the
  unfiltered list. Canonical consolidation means these variants need not
  appear independently in Google.
- Report-page footer links and language alternates omit the context query.
  Report forms reject another report page as their return context, preventing
  recursive hidden form values and redirects as well.
- Private/personalized account and candidate pages, editorial pages, errors,
  review records and rejected records retain their existing exclusions.

## Verification and limits

Before the fix, the focused SEO suite failed on archive accessibility,
expired-page indexing, empty organization indexing, filtered-list indexing,
and recursive report links. After the fix, the full SQLite suite passed
333 tests with one PostgreSQL-only skip. An additional sitemap-wide eligibility
test was then added; the final focused run passed 59 tests, including checking
that every generated sitemap URL returns HTTP 200 without `noindex`.
These runs used the existing Python 3.11 environment; production/CI target
Python 3.12. The default `.venv` lacked Pillow and could not run the tests.

Production requests to `/robots.txt` and `/sitemap.xml` from this environment
received HTTP 403, `Server: cloudflare`, body `error code: 1010`. This is an
access limitation for this client, not proof that verified Googlebot is blocked.
No deployment, Cloudflare configuration change, or GSC validation was performed.

## Remaining production acceptance

1. Deploy the reviewed changes through the existing Woodpecker process.
2. Confirm the sitemap uses `https://poslovi.aneskurtovic.com`, includes archived
   jobs and organizations without jobs, and is accessible to Google.
3. Use GSC **Test live URL** on the homepage, a current job, an archived job,
   and a formerly excluded organization. Check HTTP 200, indexing allowed,
   intended canonical and rendered content. If Google receives a challenge,
   inspect Cloudflare security events and verified-bot handling.
4. Resubmit the sitemap and request indexing of representative content pages.
   Validate the corrected noindex issue; old report variants can consolidate
   to the clean report canonical as Google recrawls them.
5. Export the two 5xx URLs and the discovered/crawled-but-not-indexed groups.
   Those issues cannot be diagnosed from the supplied noindex export.

Google's [technical requirements](https://developers.google.com/search/docs/essentials/technical)
and [noindex documentation](https://developers.google.com/search/docs/crawling-indexing/block-indexing)
distinguish eligibility from actual indexing. These changes make content
eligible; they cannot guarantee Google will index every page.
