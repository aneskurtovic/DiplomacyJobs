# DiplomacyJobs MVP backlog

Priority follows the product requirement: the board must show trustworthy, current jobs from official sources. `DesignProposal.html` defines the public visual direction; its source coverage layout now uses live data.

## P0 — Source coverage and trustworthy ingestion

- [ ] Complete resident embassy, career consulate, honorary consulate, and international organization inventory against current BiH MFA records. The ministry pass produced 96 candidates and 53 local missions; international bodies, honorary-list reconciliation, and live website checks remain.
- [ ] Source leads not yet integrated (checked 2026-10-02): ILO (jobs.ilo.org answers a SuccessFactors JSON endpoint, `POST /services/recruiting/v1/jobs`, but lists 8 jobs worldwide and ILO has no BiH office); UNESCO (same endpoint returns 401); WHO (careers.who.int is a JavaScript application); NATO HQ Sarajevo, EIB and the Austrian Embassy (no vacancy page found); ICMP (careers page moved, 404); UNOPS (server sends an incomplete certificate chain; working around certificate verification is not done). GIZ is a federal company, not an IGO, so it is out of scope. Germany posts Sarajevo job ads as standalone pages on sarajewo.diplo.de (2020, 2022) with no listing that links them; the Netherlands has no Sarajevo vacancies page (other Dutch embassies use `/about-us/vacancies-and-internships`); Spain's "Oglasi za posao" page holds one finished 2025 selection inline, without per-vacancy links, so it needs a single-page adapter if it becomes active.
- [ ] Validate official recruitment endpoints from the server network. Keep homepage, recruitment portal, and application URL separate. Record no source found, blocked, and parser failure separately.
- [x] Integrate and verify at least 10 complete operational sources before public launch. Twenty-two live-verified complete sources: Denmark, Italy, EU Delegation (EEAS, BiH-filtered and paginated), UN in BiH (country-team listing of agency jobs), OHR, EUFOR, EBRD (Sarajevo office, BA-filtered), RCC, the US Embassy (State Department ERA search for the BiH mission), Japan, Switzerland, UNDP, UNFPA, UN Women and IOM (all through the public Oracle Recruiting Cloud API, BiH duty stations only) UNHCR and the IMF (Workday JSON API, BiH country or location facet) and the Council of Europe (talents.coe.int, BiH duty stations), Ireland (embassy job-opportunities page), the UN Secretariat (careers.un.org API, BiH duty stations), the World Bank Group (Cornerstone search API, country BA), and OSCE (global portal search filtered to the BiH mission, with a result count check). Japan, Switzerland, Ireland and the OSCE search refuse non-browser TLS fingerprints; per the owner's decision they opt in to Chrome TLS impersonation (curl_cffi, `adapter_config.impersonate`). Every other source keeps the honest bot user agent. Partial: the Swedish Embassy (its news list shows only the latest five items; vacancies are posted as news). Still blocked: UK (FCDO anti-bot check) and UNICEF (AWS WAF JavaScript challenge after a few requests, even with impersonation; adapter exists; challenges are not solved). France's site has no jobs page. Germany, Sweden, Norway, Netherlands, Czechia, Hungary and Poland have no vacancy page; Spain's page only logs one selection process. An inaccessible source does not count.
- [ ] Handle active-list pagination and changed page structure without falsely closing existing jobs. Partial feeds now refresh known published jobs directly but still need a complete listing endpoint.
- [x] Limit collection to 2026: skip links in clearly dated older URL archives before detail fetch, cap detail fetches at 100 per source, and persist only candidates supported by a 2026 publication date, URL year, or deadline. Deadline-only leads remain in admin review. No historical archive import.
- [ ] Publish only proven current, paid, BiH-based individual roles posted in 2026 (or with a 2026 deadline where publication date is absent). Keep uncertain entries in admin review. OSCE's current 2026 Sarajevo vacancy is live-verified and published locally.
- [ ] Run the daily fetch from Hetzner, verify successful empty listings versus failures, and inspect resulting public jobs.

## P1 — Operations and data quality

- [x] Django models, admin, public list, source coverage page, scheduler command, source run history, and optional AI batch interface are implemented.
- [x] Unit tests run with `manage.py test` (EEAS, UN, OHR, EUFOR, EBRD, RCC, ERA, Japan, Oracle, Workday, CoE, OSCE adapters, date parsing, registry import, challenge-response handling, Denmark, Italy, and the publish/close rules of a full ingest run).
- [x] Query parameters remain in job URLs; fetch failures and excessive link counts prevent absence-based closure.
- [ ] Validate a full deployment on the actual Hetzner host and HTTPS subdomain, including migrations, backup restore, static assets, source access, and scheduled runs.
- [x] Confirm AI imports and manual corrections survive subsequent source updates; handle changed source text through review. A source change after AI enrichment stays in review until a reviewer acts.
- [ ] Add source-specific handling for PDFs, dynamically rendered portals, and paid internships only where an official source requires it.

- [ ] Accent-insensitive search: SQLite folds case only for ASCII and neither database ignores diacritics, so "svicarska" does not find "Švicarska". On PostgreSQL, add `django.contrib.postgres` with the `unaccent` extension and test it against PostgreSQL (the drafted CI workflow in `.github/workflows/tests.yml` runs the suite on both databases once it can be pushed).

## P2 — Public design

- [x] Apply `DesignProposal.html` typography, colors, header, coverage summary, legend, and source table to the real `/sources/` page. Replace all mock numbers and statuses with database values.
- [x] Carry the same visual language into the jobs page; retain responsive search, filters, and official application links.

## Current constraints

The registry contains 70 organizations. Twenty-two complete sources are enabled after live checks, which clears the ten-source launch gate. The full international and honorary inventory and the Hetzner deployment are outstanding. Public counts must reflect this reality rather than the mock figures in the design proposal.
