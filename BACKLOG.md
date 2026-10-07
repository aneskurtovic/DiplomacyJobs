# DiplomacyJobs MVP backlog

Scope and launch gates are in [PLAN.md](PLAN.md). Current counts, verification results and the ordered next steps are in [HANDOFF.md](HANDOFF.md); this file does not repeat them.

## P0 — Source access and content coverage

- [ ] Romania remains unavailable: sarajevo.mae.ro and www.mae.ro require a JavaScript browser check; cariera.mae.ro is a login-only platform. No challenge solving.
- [ ] Still blocked: UK (FCDO "Quick Check" on every fco.tal.net page) and UNICEF's listing (AWS WAF; per-IP limit so strict that the second request within seconds is challenged, even with `request_delay`). Recheck UNICEF from the Hetzner network; its jobs also arrive through aggregators.
- [ ] Restore or replace the three enabled feeds still failing from Hetzner: Sweden (#26, HTTP 403), UN Careers (#51, API HTTP 504), and ReliefWeb (#53, HTTP 202 challenge). Keep them visible as unavailable. [ReliefWeb's API requires a pre-approved appname](https://apidoc.reliefweb.int/parameters); none is configured, and the older HTML approach previously worked. Investigate an approved access path if this feed remains important.
- [x] Malaysia and Pakistan are sources (2026-10-03): their missing intermediates are fetched from the certificate's own AIA link and verified to a trusted root (`scripts/cert_chain.py`, `data/intermediates/`, `adapter_config.intermediates`). Qatar's site, now readable the same way, has no recruitment section; Russia's official Telegram channel has never posted a vacancy. Both are "no local recruitment list".

## P1 — Deployment and operations

- [ ] Revisit the dated "no local recruitment list" findings before their 90-day expiry (checked 2026-10-02/03; 33 organizations in the 2026-10-03 snapshot).
- [ ] Add source-specific handling for PDFs and JavaScript-rendered portals only where an official source requires it.
- [ ] For UNICEF jobs found via aggregators, read the "Advertised" date from the jobs.unicef.org detail page to prove the year instead of leaving them in review.
- [ ] Set a retention policy before trimming stored text of long-closed jobs.
- [ ] Open question: now that INGOs are in scope, decide whether to add ICRC (earlier excluded as outside the mission/IGO scope).

- [ ] Run the five-person mobile usability check ([script](docs/design/usability-check.md)); it needs real participants, ideally on the deployed site.

## P2 — Job pages and enrichment

- [ ] Configure `ADMINS` and an e-mail backend on the server so visitor reports are e-mailed, not only listed in admin.
- [ ] Requirements for UNDP consultancy notices live in the attached ToR documents, not in the notice text; read those to fill education and experience.
- [ ] Translate the remaining public jobs with `/translate-jobs` when the owner asks. Translation is on demand only (owner decision 2026-10-07).
- [ ] Employer names on the English site come from the Bosnian registry (e.g. "UNDP u Bosni i Hercegovini"); add English names if wanted.

## P2 — App track

The front-end stays server-rendered with htmx and plain JavaScript only where needed; no framework (owner decision 2026-10-07, see HANDOFF).

- [ ] Check installation and offline reading on a real Android and iOS phone after deploy.
- [ ] Optional: push notifications for a saved search (needs a stored subscription per visitor).

## Done

- [x] "Viša škola" (junior college) education level, and quote-checked AI proposals for education, experience and fields of study through `export_enrichment`/`import_enrichment` and `/enrich-jobs` (2026-10-07). Run `extract_requirements` on the server after deploy. Details in HANDOFF.
- [x] Woodpecker is the only CI; the GitHub Actions workflow was removed (2026-10-07). Haiku subagents added: `translator` (used by `/translate-jobs`) and `source-scout` (read-only source and lead investigations).
- [x] Installable site and htmx job-list filters (2026-10-07 evening): manifest, icons, service worker with offline job pages and an offline page; filters, chips, sort and pages update `#results` in place with clean pushed URLs, without breaking the plain form. Details in HANDOFF.
- [x] Phone job list polish (2026-10-07): two-row search box with an icon-only Filteri, sort and feed on one row; first job at 488px instead of 602px. "+n" tag no longer wraps alone, consistent back links, no current tab on error pages.
- [x] Site error pages and screenshot review (2026-10-07): own 400, 403, CSRF-failure, 404, 410 and 500 pages in Bosnian and English on a shared layout (`board/error.html`); every public page checked at 390, 768 and 1280px in light and dark. Phone job cards one row shorter, no duplicated facts on the job page under 960px, sources table text no longer cut off on phones, report form fields and radios fixed in dark mode and enlarged for touch. CI fix: page-rendering tests need plain static storage. Details in HANDOFF.
- [x] Hetzner launch (2026-10-07): HTTPS at `poslovi.aneskurtovic.com`, migrated and imported registry, scheduled daily scrape, Woodpecker tests and deploy, separate database and role in the existing PostgreSQL instance, and a checked backup restore. The first server scan distinguished 49 successful sources (including empty results) from three failures; public jobs were inspected.
- [x] Staff editorial queue at `/editor/` (2026-10-07): source evidence, corrections, verification note, save/publish/reject actions, and publication guards. An admin shortcut points to it; advanced settings remain in Django admin.
- [x] Reconcile aggregator copies of official vacancies after each scrape or with `reconcile_duplicates` (2026-10-07). Eight existing Impactpool copies were closed as duplicates in production, leaving no pending review jobs.
- [x] Kuwait checked by the owner (2026-10-03): no embassy website and no MFA vacancies; recorded as "no local recruitment list".

- [x] Employer pages and related jobs (2026-10-03): `/sources/<id>/<slug>/` per organization, linked from `/sources/`, the job card's employer line and the job page. Each page shows its source status with the recruitment audit note and evidence link, current jobs, then paginated past jobs. Past jobs are those once published (new `Job.published_at`), never ones a reviewer closed. Syndicated jobs appear under their registry employer, and under the aggregator only when the employer is unknown. A page is indexed and in the sitemap only when it lists a job. On the job page, "Drugi oglasi istog poslodavca" (up to 3, aggregator copies included) and "Slične pozicije" (`board/related.py`: rule-based; needs a shared title word about the work plus one more signal, from another employer) are left out when empty. On the 23 current jobs, only the three EU4People/Balkans programme jobs get suggestions.

- [x] Design system Phase 3 (2026-10-03): `/sources/` grouped by state with the four stat cards as filters, a coverage bar and a name search; dark theme on (follows the OS) after a contrast check of every page; forced-colours borders; employer monograms from `Organization.short_name`; a 1200×630 Open Graph image per published job (`/jobs/<id>/share.png`, Pillow). The usability check is still open.
- [x] Design system Phase 2 (2026-10-03): search bar with a "Filteri" disclosure, removable filter chips and sort links; trust strip under the hero; job card v2 (whole card links to the job page, deadline column with an urgency countdown, at most three tags); `{% deadline job %}` tag shared by the card, the job summary and the sticky apply bar under 960px; restyled evidence quotes; self-hosted Public Sans and IBM Plex Mono.
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
