# Scraper investigation — 2026-11-17

Read-only inspection of Hetzner production at deployed commit `f8d5f42`, around 13:20–13:30 UTC. Web and scraper containers were running; web health was healthy. No production database changes, migrations, restarts, or deployment were performed. Parser validation loaded local code only into a short-lived Python process and called discovery/candidate functions without ingestion.

## Production evidence

The preceding seven days contained 4,169 successful and 556 failed scrape attempts. The database contained 15 published jobs, three in review, and 262 closed jobs. Attempt counts do not measure how many vacancies are missing.

| Source | Consecutive failures at inspection | Evidence and diagnosis |
| --- | ---: | --- |
| ReliefWeb #53 | 362 | No successful scan recorded. RSS returns HTTP 202 HTML instead of a feed; 84 failed attempts in seven days. Existing handoff documents the requirement for an approved API appname. |
| Switzerland #21 | 155 | Last success November 4. Old URL redirects to `www.schweiz-bosnienundherzegowina.eda.admin.ch//en`, the new homepage. Its [job vacancies page](https://www.schweiz-bosnienundherzegowina.eda.admin.ch/en/job-vacancies) refers applicants to the federal jobs portal. Allowing the redirect would let the old parser return an empty list from a homepage. Coverage requires following the new recruitment channel, not merely extending the host allowlist. |
| Greece #11 | 146 | Last success November 5. Old Elxis URL returns 404. The [new embassy news listing](https://www.mfa.gr/bosnia-herzegovina/en/category/news/embassy-news/) uses WordPress cards, different date/content selectors, and `/page/2/` pagination. |
| Canada #25 | 107 | Last success November 8. Live Gatsby bundle contains 195 mission records and 20 job records. Job array changed to a double-quoted `JSON.parse` argument containing JavaScript hex escapes such as `\x3c`. Parser previously recognized only single-quoted arguments. |
| EEAS #6 | 95 | Last success November 9. HTTP 403 page explicitly states `Disallowed by robots.txt`. Needs an approved access route or verified alternative official feed. One published job currently belongs to this source. |
| World Vision #61 / UNHCR #37 / IMF #38 | 15 / 15 / 5 | HTTP 429s from Workday HTML pages. UNHCR HTML and JSON API initially answered 200 during inspection; all three JSON endpoints answered 429 on a later probe. An unnecessary initial HTML fetch is one avoidable failure point, but removing it does not eliminate upstream API throttling. World Vision and UNHCR have three and one published jobs respectively. |

Other sources mostly recovered after transient failures. Impactpool had nine failures in seven days because `/jobs/1246759/apply` returned a 303 to its own job page; `httpx.raise_for_status()` treats this as an exception. Türkiye/Sarajevo's latest attempt failed with 404, but it had succeeded that morning. Other intermittent failures included Hilfswerk timeouts, ERA disconnects, Spain timeouts/403, and scattered upstream server errors.

## Local changes

- Canada parses both quote styles and JavaScript hex escapes as literals; scraped JavaScript is never executed. Existing mission/employer/date checks remain in place.
- Workday starts directly with its JSON API, avoiding the redundant HTML request.
- Greek registry settings and migration move the existing source to the new official news URL, preserving its ID, jobs, run history, enabled state, and failure history. Generic pagination can follow the site's next-page links with same-origin/path and cycle checks. Missing listing cards or malformed later pages fail rather than becoming successful empty scans.
- Impactpool internal application redirects provide no verified employer application URL, instead of failing the entire source. Existing publication-year checks keep unverified records in review.
- Scheduled failures back off to 2, 4, 8, 16, then 24 hours. A successful ingest resets the failure counter and restores the normal interval. The configured minimum interval still applies, including the once-daily UNDP procurement limit. Manual `scrape_jobs --source ID` remains available for controlled verification after a fix.

## Validation and remaining work

Regression cases reproduced the Canadian array error, Workday HTML 429, Impactpool 303, and incorrect Greek pagination before their fixes. Django checks and migration drift checks pass. Full local suite: 329 tests, one skipped. Targeted tests also pass after the live Canadian hex-escape finding was added.

Read-only live validation from Hetzner using patched code successfully parsed Canada and Greece, each returning zero matching local job candidates. Canada's complete upstream arrays were present; this is a filtered result, not an interpretation of a blocked response as empty. Workday API access remained intermittent/rate limited, so its recovery is not claimed.

These changes are local and have not restored production scraping yet. Deployment and migration are required for them to take effect. Switzerland still needs integration with its new recruitment channel; EEAS needs permitted access; ReliefWeb needs an approved API appname and integration. Keep these sources visibly unavailable until complete, validated scans succeed. Missing or stale coverage cannot be quantified from the failed attempts alone.
