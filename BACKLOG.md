# DiplomacyJobs MVP backlog

Priority follows the product requirement: the board must show trustworthy, current jobs from official sources. `DesignProposal.html` defines the public visual direction; its source coverage layout now uses live data.

## P0 — Source coverage and trustworthy ingestion

- [ ] Complete resident embassy, career consulate, honorary consulate, and international organization inventory against current BiH MFA records. The ministry pass produced 96 candidates and 53 local missions; international bodies, honorary-list reconciliation, and live website checks remain.
- [ ] Validate official recruitment endpoints from the server network. Keep homepage, recruitment portal, and application URL separate. Record no source found, blocked, and parser failure separately.
- [x] Integrate and verify at least 10 complete operational sources before public launch. Eleven live-verified complete sources: Denmark, Italy, EU Delegation (EEAS, BiH-filtered and paginated), UN in BiH (country-team listing of agency jobs), OHR, EUFOR, EBRD (Sarajevo office, BA-filtered), RCC, the US Embassy (State Department ERA search for the BiH mission), Japan and Switzerland. OSCE's recent-jobs feed works but has partial coverage. Japan and Switzerland refuse non-browser TLS fingerprints; per the owner's decision they opt in to Chrome TLS impersonation (curl_cffi, `adapter_config.impersonate`). Every other source keeps the honest bot user agent. Still blocked: UK (FCDO anti-bot check) and UNICEF (AWS WAF JavaScript challenge after a few requests, even with impersonation; adapter exists; challenges are not solved). UNDP, UNHCR, IOM and Council of Europe answer with impersonation but have no adapter yet. France's site has no jobs page. Germany, Sweden, Norway, Netherlands, Czechia, Hungary and Poland have no vacancy page; Spain's page only logs one selection process. An inaccessible source does not count.
- [ ] Handle active-list pagination and changed page structure without falsely closing existing jobs. Partial feeds now refresh known published jobs directly but still need a complete listing endpoint.
- [x] Limit collection to 2026: skip links in clearly dated older URL archives before detail fetch, cap detail fetches at 100 per source, and persist only candidates supported by a 2026 publication date, URL year, or deadline. Deadline-only leads remain in admin review. No historical archive import.
- [ ] Publish only proven current, paid, BiH-based individual roles posted in 2026 (or with a 2026 deadline where publication date is absent). Keep uncertain entries in admin review. OSCE's current 2026 Sarajevo vacancy is live-verified and published locally.
- [ ] Run the daily fetch from Hetzner, verify successful empty listings versus failures, and inspect resulting public jobs.

## P1 — Operations and data quality

- [x] Django models, admin, public list, source coverage page, scheduler command, source run history, and optional AI batch interface are implemented.
- [x] Unit tests run with `manage.py test` (EEAS, UN, OHR, EUFOR, EBRD, RCC, ERA adapters and challenge-response handling). Extend to Denmark/Italy/OSCE and the publish/close rules.
- [x] Query parameters remain in job URLs; fetch failures and excessive link counts prevent absence-based closure.
- [ ] Validate a full deployment on the actual Hetzner host and HTTPS subdomain, including migrations, backup restore, static assets, source access, and scheduled runs.
- [ ] Confirm AI imports and manual corrections survive subsequent source updates; handle changed source text through review.
- [ ] Add source-specific handling for PDFs, dynamically rendered portals, and paid internships only where an official source requires it.

## P2 — Public design

- [x] Apply `DesignProposal.html` typography, colors, header, coverage summary, legend, and source table to the real `/sources/` page. Replace all mock numbers and statuses with database values.
- [x] Carry the same visual language into the jobs page; retain responsive search, filters, and official application links.

## Current constraints

The registry contains 60 organizations. Nine complete sources and one partial source are enabled after live checks. The full international and honorary inventory, ten-source launch gate, and Hetzner deployment are outstanding. Public counts must reflect this reality rather than the mock figures in the design proposal.
