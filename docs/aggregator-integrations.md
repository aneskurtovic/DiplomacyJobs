# International job aggregators

ReliefWeb (BiH country filter C40) and Impactpool (work-location filter 28) extend
the official-source inventory. Both adapters are implemented (`board/aggregators.py`)
and registered as enabled sources under organizations of kind `aggregator`.

The board and Atom feed choose one record per vacancy, preferring the direct
employer. Source records, snapshots, manual edits and scan lifecycles remain
independent. A syndicated record cannot reopen an official record held for review,
withdrawn, disabled or closed. This decision is recomputed when reading the board,
so scrape order and admin changes cannot leave a stale duplicate flag.

Matching uses the original vacancy/application URL (tracking removed, requisition
parameters retained), with a specific UNICEF requisition URL normalization. The
fallback requires an exact normalized title, an explicitly matched employer,
the same nonempty city and the same deadline. Similar titles are insufficient.
Publication dates more than 45 days apart represent separate recruitment rounds.
Shared careers homepages do not identify a vacancy. Unknown employer aliases and
uncertain matches stay separate. Aggregator employer names are retained in field
evidence, used by the board, filters and Atom, and shown with portal attribution.

## Adapter behaviour

- Listings are paginated HTML; the stated result count must match the collected
  links, otherwise the scan fails without closing jobs.
- ReliefWeb: posted/closing dates come from `<time datetime>`; country tags sit in
  the article `<footer>`, so aggregator detail pages are fetched with
  `fetch(..., keep=("footer",))`. Multi-country (regional) jobs are eligible only
  when the text names BiH as a place of residence/work; they carry an eligibility note.
- Impactpool: no publication date is published, so its jobs go to review rather
  than inventing one. The original application URL is read from the `/apply`
  redirect without following it.

## Edge cases found in the live check (2026-10-03)

| Case | Handling |
| --- | --- |
| ReliefWeb country tags inside `<footer>` were stripped by `fetch` | `keep=("footer",)` for aggregator detail pages |
| Impactpool links Oracle `/sites/CX_1/requisitions/job/N`; our UNDP/UN Women adapter stores `/sites/CX_1/job/N` | `url_key` normalizes Oracle Candidate Experience locale, `requisitions/` and `preview/` variants; the site (CX_1 vs CX_1001) stays part of the key |
| Impactpool and Oracle deadlines differ by one day (UTC vs local) | Matched by URL; the exact-deadline fallback is kept strict on purpose |
| UNFPA links its own unfpa.org page instead of Oracle | Matched by the exact title/employer/city/deadline fallback |
| UNICEF jobs only reachable via Impactpool (our UNICEF source is blocked) | New coverage; kept in review because the year is not proven |

Live result: ReliefWeb 1 job (International Detention Coalition, regional Balkans,
published). Impactpool 8 jobs: 6 are duplicates of official records (UNDP x3,
UN Women, UNFPA, OSCE) and stay hidden; 2 UNICEF national consultancies are new.

Verification: 164 tests, 163 passed and one PostgreSQL-only skip.
