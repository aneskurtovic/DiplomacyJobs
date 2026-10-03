# DiplomacyJobs MVP backlog

Scope and launch gates are in [PLAN.md](PLAN.md). Current counts, verification results and the ordered next steps are in [HANDOFF.md](HANDOFF.md); this file does not repeat them.

## P0 — Coverage and content review (owner priority, 2026-10-03)

- [ ] **GIZ via a third-party board.** The owner has approved this. GIZ advertises BiH national posts on mreza-mira.net; add a source filtered to GIZ, attributed to the portal. See [employer check](docs/ngo-donor-employers-2026-10-03.md).
- [ ] **UNDP individual-consultant notices.** These appear on UNDP's procurement-notices system, which the UNDP Oracle source does not read; add a source for BiH notices.
- [ ] **Complete the four partial sources:** Sweden (news list shows only the latest five items), RYCO (first page of its vacancies-and-tenders category only), Brazil (open scanned PDFs need OCR or manual handling), Canada (no source for the Sarajevo honorary consulate's own notices). Failed or partial scans must keep preserving existing jobs.
- [ ] **Resolve the 15 sites that could not be accessed or rendered** in the [2026-10-03 audit](docs/source-audit-2026-10-03.md): Holy See, Malaysia, Romania, Ukraine, Greece, Pakistan, Indonesia, Russia, Slovakia, Order of Malta, Kuwait, Qatar, and the honorary consulates of Cyprus, DR Congo and Bangladesh (Sarajevo). No JavaScript-challenge solving and no TLS weakening. Recheck from the deployment network where local access fails.
- [ ] Still blocked: UK (FCDO anti-bot check) and UNICEF's listing (AWS WAF JavaScript challenge; UNICEF jobs also arrive through the aggregators). UNICEF job detail pages on jobs.unicef.org were reachable on 2026-10-03.

## P1 — Deployment and operations

- [ ] Deploy to the Hetzner host with an HTTPS subdomain: migrations, static assets, `import_registry`, `verify_sources` from the server network, daily scheduled scrape, and a verified backup restore.
- [ ] After the first server runs, confirm that successful empty listings are distinguished from failures and inspect the public jobs.
- [ ] Revisit the 23 "no local recruitment list" findings before their 90-day expiry (checked 2026-10-03).
- [ ] Add source-specific handling for PDFs and JavaScript-rendered portals only where an official source requires it.
- [ ] Aggregator copies of vacancies already held from the employer's own source land in review ("year not proven") on every first sighting, although the board already hides them. Close or auto-resolve them at ingest so the review queue holds only real decisions.
- [ ] For UNICEF jobs found via aggregators, read the "Advertised" date from the jobs.unicef.org detail page to prove the year instead of leaving them in review.
- [ ] Set a retention policy before trimming stored text of long-closed jobs.
- [ ] Open question: now that INGOs are in scope, decide whether to add ICRC (earlier excluded as outside the mission/IGO scope).

## Done

- [x] Django models, admin, public jobs and `/sources/` pages, Atom feed, scheduler command, run history, optional AI enrichment interface.
- [x] `DesignProposal.html` applied to `/sources/` and the jobs page using real database values.
- [x] More than ten complete official sources integrated and live-checked locally (2026-10-02 and 2026-10-03); see HANDOFF for the count and [integration notes](docs/recruitment-integrations-2026-10-03.md).
- [x] 2026-only collection: older dated archives skipped before detail fetch, 100 detail fetches per source, deadline-only leads kept in review.
- [x] Audit of all 46 previously unchecked coverage entries, with dated evidence kept separate from presence and scrape dates ([audit](docs/source-audit-2026-10-03.md)); the seven integration leads it found are enabled (five complete, two partial).
- [x] Aggregators ReliefWeb and Impactpool with cross-source deduplication that prefers the direct employer ([notes](docs/aggregator-integrations.md)).
- [x] INGOs Save the Children and CRS enabled on the `oracle` adapter under the `ngo` organization kind.
- [x] Production reliability: console tracebacks with DEBUG off, scheduler connection cleanup, per-source exception isolation, PostgreSQL connection-recovery test.
- [x] Linux/Python 3.12 CI on SQLite and PostgreSQL 16, passing on every push.
- [x] AI imports and manual corrections survive source updates; a source change after enrichment returns the job to review.
- [x] Pagination links keep only active filters; missing pages return 404; indexed snapshot lookup; `PUBLIC_BASE_URL` for canonical, Open Graph, sitemap and robots URLs; admin run and snapshot filters.
- [x] Accent-insensitive search on the board and feed.
- [x] Rechecked the 2026-10-02 dead-end leads (2026-10-03): UNOPS (`avature`), EIB (`peoplesoft`) and Germany (`sitemap`) enabled; Austria and the Netherlands have no vacancy page. Details in HANDOFF.
- [x] Content review of all 21 open jobs (2026-10-03): 15 published, 6 aggregator duplicates closed; details in HANDOFF.
- [x] Bulk publish skips jobs that have a review reason; bulk publish, close and renew write admin history. The RYCO Tirana job published in error was closed (`manual`).
