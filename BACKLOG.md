# DiplomacyJobs MVP backlog

Scope and launch gates are in [PLAN.md](PLAN.md). Current counts, verification results and the ordered next steps are in [HANDOFF.md](HANDOFF.md); this file does not repeat them.

## P0 — Coverage and content review (owner priority, 2026-10-03)

- [ ] Still unavailable: Malaysia, Pakistan, Qatar (incomplete certificate chains), Romania, Russia (JavaScript browser checks), Kuwait (Cloudflare challenge). No challenge solving, no TLS weakening.
- [ ] Still blocked: UK (FCDO anti-bot check) and UNICEF's listing (AWS WAF JavaScript challenge; UNICEF jobs also arrive through the aggregators). UNICEF job detail pages on jobs.unicef.org were reachable on 2026-10-03.

## P1 — Deployment and operations

- [ ] Deploy to the Hetzner host with an HTTPS subdomain: migrations, static assets, `import_registry`, `verify_sources` from the server network, daily scheduled scrape, and a verified backup restore.
- [ ] After the first server runs, confirm that successful empty listings are distinguished from failures and inspect the public jobs.
- [ ] Revisit the 30 "no local recruitment list" findings before their 90-day expiry (checked 2026-10-02/03).
- [ ] Add source-specific handling for PDFs and JavaScript-rendered portals only where an official source requires it.
- [ ] Aggregator copies of vacancies already held from the employer's own source land in review ("year not proven") on every first sighting, although the board already hides them. Close or auto-resolve them at ingest so the review queue holds only real decisions.
- [ ] For UNICEF jobs found via aggregators, read the "Advertised" date from the jobs.unicef.org detail page to prove the year instead of leaving them in review.
- [ ] CI notices (run 37116293201): actions/checkout@v4 and actions/setup-python@v5 target the deprecated Node.js 20; `ubuntu-latest` moves to Ubuntu 26 from 2026-10-19. Update the action versions (needs a token with `workflow` scope).
- [ ] Set a retention policy before trimming stored text of long-closed jobs.
- [ ] Open question: now that INGOs are in scope, decide whether to add ICRC (earlier excluded as outside the mission/IGO scope).

- [ ] Design system Phases 2–3 ([proposal](docs/design/design-system.html)): filter bar with removable chips, job card v2 with a deadline component, mobile sticky apply bar, trust strip, self-hosted fonts, then grouped `/sources/` and a dark theme QA pass. Awaiting owner review.

## P2 — Job pages and enrichment

- [ ] Configure `ADMINS` and an e-mail backend on the server so visitor reports are e-mailed, not only listed in admin.
- [ ] Requirements for UNDP consultancy notices live in the attached ToR documents, not in the notice text; read those to fill education and experience.
- [ ] Optionally extend `export_enrichment`/`import_enrichment` to propose requirement fields, with the same quote checks.
- [ ] Translate the remaining public jobs with `/translate-jobs`; decide whether translation runs after every scrape or on demand.
- [ ] "Junior college" / "viša škola" has no education level between secondary school and a bachelor's degree; consider adding one.
- [ ] Employer names on the English site come from the Bosnian registry (e.g. "UNDP u Bosni i Hercegovini"); add English names if wanted.

## Done

- [x] Design system Phase 1 (2026-10-03): design tokens (`board/static/board/tokens.css`) adopted in site.css; two-row mobile header fixes the horizontal overflow at 320–390px; `:focus-visible` outline; input borders at 3.66:1; violet review status on `/sources/`; SVG icons instead of emoji/glyphs. Dark mode is defined but off.
- [x] English interface at `/en/`, and Bosnian/English advert versions imported from the local `/translate-jobs` skill (2026-10-03).
- [x] Job pages (`/jobs/<id>/<slug>/`) with rule-based requirements (education, field, experience, languages, licence, citizenship, terms), quotes and admin overrides; board filters by education, experience and field; visitor problem reports with admin queue (2026-10-03).
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
- [x] UNDP individual-consultant notices (`undpnotices`, owner approved reading despite robots.txt) and Indonesia (`kemlu` public API with section counts) enabled (2026-10-03).
- [x] Rechecked the 15 inaccessible sites (2026-10-03): Greece enabled; 7 have no local recruitment list; Indonesia awaits proof of a complete API list; 6 remain unavailable. Details in HANDOFF.
- [x] Completed the four partial sources (2026-10-03): Sweden (pagination), RYCO (WordPress API, Sarajevo category), Brazil (scanned adverts become review items), Canada (LES portal is GAC's only channel). Details in HANDOFF.
- [x] GIZ via mreza-mira.net (owner-approved third-party board): `wordpress` adapter filtered to GIZ titles, attributed to the portal on the board (2026-10-03).
- [x] Rechecked the 2026-10-02 dead-end leads (2026-10-03): UNOPS (`avature`), EIB (`peoplesoft`) and Germany (`sitemap`) enabled; Austria and the Netherlands have no vacancy page. Details in HANDOFF.
- [x] Content review of all 21 open jobs (2026-10-03): 15 published, 6 aggregator duplicates closed; details in HANDOFF.
- [x] Bulk publish skips jobs that have a review reason; bulk publish, close and renew write admin history. The RYCO Tirana job published in error was closed (`manual`).
