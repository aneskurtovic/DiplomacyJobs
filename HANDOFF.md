# DiplomacyJobs continuation handoff

Updated: 2026-10-07 (Europe/Sarajevo). This file records current counts and verification results; [PLAN.md](PLAN.md) holds scope and launch gates, [BACKLOG.md](BACKLOG.md) the work list. Dated sections below preserve their original observations.

## Current state (verified 2026-10-07, Hetzner PostgreSQL)

- **Code and CI:** `main` carries the installable site and htmx job-list filters of 2026-10-07 (evening; migration 0037 unchanged). Local full suite: 265 tests, one SQLite skip, on Python 3.12 with `requirements.lock`, without collected static files, as CI runs. Woodpecker is the only CI (owner decision 2026-10-07); the GitHub Actions workflow was removed. The live site serves `/manifest.webmanifest`, `/sw.js` and `/en/offline/` and answers `HX-Request` with the partial, so Woodpecker deployed it.
- **Production:** [poslovi.aneskurtovic.com](https://poslovi.aneskurtovic.com/) serves through Caddy with HTTPS. Web and scraper containers use a dedicated `diplomacyjobs` database and role in the existing PostgreSQL 16 instance. The daily scrape is scheduled for 06:00 Sarajevo time; a daily database backup is installed and a scratch-database restore was verified. `/health/` returns 200.
- **Registry:** 87 organizations and 59 sources were imported; 52 sources are enabled. From the first Hetzner scrape, 49 succeeded and three were unavailable: Sweden (#26, HTTP 403), UN Careers (#51, API HTTP 504), ReliefWeb (#53, HTTP 202 challenge). `/health/scrape/` still returns 503 for those three; this is visible as unavailable coverage, not zero jobs.
- **Jobs:** 21 published, 0 in review, 188 closed; eight of the closed records are syndicated copies marked `duplicate`. The staff queue is at `/editor/`, with Django admin at `/admin/` for source settings and advanced records. There are 21 currently visible public jobs awaiting Bosnian/English advert versions.

## Tooling decisions (owner, 2026-10-07)

- **CI is Woodpecker only.** `.woodpecker/test.yml` runs Django checks, migration drift and the suite on SQLite and PostgreSQL 16; `deploy.yml` deploys `main` after it. `.github/workflows/` was deleted; do not add GitHub Actions back.
- **Translations run only on demand** (`/translate-jobs`), never after a scrape. Untranslated jobs show the source text.
- **Haiku subagents** do the bulk work: `.claude/agents/translator.md` writes advert versions in parallel batches that the main session imports and spot-checks; `.claude/agents/source-scout.md` investigates sources, blocked sites, the 90-day audit and new employers or fields, read-only, under the source access policy, and reports a verdict with evidence. The main session decides and changes the registry or code. Both use the `haiku` model alias, so they follow the current Haiku model.

## Front-end approach (owner decision, 2026-10-07)

- Pages stay server-rendered Django templates. No JavaScript framework (React, Vue, Svelte, Next.js and the like): the site is a public, search-indexed content site with Bosnian/English gettext, share images and pages that work without JavaScript.
- App-like interactions use **htmx**: Django returns HTML fragments that htmx swaps into the page (for example instant filtering, "load more" instead of page links, sending the report form in place). Every such interaction keeps a plain link or form underneath, so the page still works if the script does not load.
- Other behaviour uses small, plain JavaScript only when needed, written by hand and self-hosted like the fonts; no build step and no npm toolchain in the Docker image.
- Done on this track (2026-10-07 evening): installable site and htmx job-list filters, see below. Push notifications for saved searches remain optional.

## Owner decisions (2026-10-03)

- A full reconciliation against the BiH Ministry of Foreign Affairs directory is **not** needed. The registry is the set of employers we choose to monitor.
- GIZ may come in through a third-party board (mreza-mira.net). More generally, aggregators and local boards are acceptable sources; the direct employer is preferred and syndicated jobs are attributed.
- INGOs and development agencies hiring in BiH are in scope (Save the Children and CRS are enabled).
- Next work, in this order: review published jobs (done 2026-10-03), then coverage (recheck the 2026-10-02 dead-end leads (done 2026-10-03), GIZ (done 2026-10-03), UNDP consultant notices (done 2026-10-03), the four partial sources (done 2026-10-03), the 15 inaccessible sites (rechecked 2026-10-03)).
- UNDP individual-consultant notices: read the official procurement-notices site despite its robots.txt `Disallow: /` (owner decision 2026-10-03). One daily POST search, BiH reference prefix only.

## Content review (2026-10-03)

All 21 open jobs were checked against the publication rule; each change has an admin history entry ("Content review 2026-10-03"). Database backup: `backups/db-before-content-review-20261003-111411.sqlite3`.

- **Kept published (13):** OSCE Chief General Services, EUSR Head of Communications, two EU twinning assistants, two EUFOR posts, US Embassy Electrical Engineer Supervisor, three UNDP posts, UNFPA PME Analyst, UN Women Family Law consultant, IDC Europe Programme Officer (regional remote role; BiH is an allowed place of work, EUR 30–40k).
- **Corrected:** EUSR job gained an EU-citizens-only eligibility note; the two twinning assistant jobs (local hire, up to EUR 2,000 gross/month) were set to national scope.
- **Published from review (2):** the two UNICEF EU4People consultancies (via Impactpool). jobs.unicef.org shows them advertised 01 Oct 2026, closing 15 Oct 2026.
- **Closed as duplicates (6):** Impactpool copies of the OSCE, UNDP (3), UNFPA and UN Women jobs already held from the employer's own source (`closed_reason=manual`, `field_evidence.duplicate_of`). Their Impactpool deadlines were a day later than the employer's, so the employer record stays authoritative.

## Dead-end leads rechecked (2026-10-03)

The five leads that found nothing on 2026-10-02 were rechecked live; three are now enabled sources (0 BiH jobs today), two remain without a vacancy page. Database backup: `backups/db-before-new-lead-sources-*.sqlite3`.

- **UNOPS:** jobs.unops.org (incomplete certificate chain) now redirects to careers.unops.org, an Avature portal whose certificate verifies normally. Enabled on the `avature` adapter (the former `coe` adapter, generalized; migration 0028 renames it) with all pages read and BiH duty stations kept: 74 jobs worldwide, none in BiH.
- **EIB:** the EIB Group's PeopleSoft portal publishes every vacancy in a public Atom feed marked complete. Enabled on the new `peoplesoft` adapter: 30 jobs, all in Luxembourg. EIB was not in the registry before.
- **Germany:** still no vacancy list, but the embassy's daily sitemap lists every article, including its stand-alone job adverts (2020, 2022). Enabled on the new `sitemap` adapter, which reads articles newer than `min_article_id` and keeps those titled as adverts: 4 new articles, none an advert.
- **Austria:** the embassy moved to `bmeia.gv.at/oeb-sarajewo`; it has no vacancy section. Added to the registry as "no local recruitment list" (it was missing).
- **Netherlands:** confirmed again: no vacancies page on netherlandsandyou.nl.

## GIZ via mreza-mira.net (2026-10-03)

- New organization kind `agency` (development agency) for GIZ, and a new `wordpress` adapter (migration 0029). It reads mreza-mira.net's public WordPress REST API: every 2026 post in Poslovi (9) and Volonterski angažman i internships (1272), excluding Arhiva (5885), where expired posts move. Posts titled as GIZ adverts are kept.
- The board labels these jobs "putem mreza-mira.net" with an "Oglas / prijava" button, as for aggregators (`Job.via`, `adapter_config.portal_name`).
- Live run: success, no GIZ advert in 2026. Run against 2025, it found the two known GIZ adverts (internship, Technical Advisor) with correct dates and city. The deadline parser now also reads "application documents by …" and "ističe …".
- The site answers HTTP 406 to a bare `Mozilla/5.0` user agent but accepts the project's bot user agent; robots.txt allows crawling.

## Partial sources completed (2026-10-03)

- **Sweden:** the news list is paginated (`?page=2` …, about 30 items in all); the earlier "latest five only" note was wrong. Generic lists can now page through (`page_item_selector`, `second_page`); all pages are read until the first empty one.
- **RYCO:** replaced the first-page category scrape by RYCO's WordPress REST API (`wordpress` adapter): every 2026 post in Vacancies (136) carrying the Local Branch Office Sarajevo category (110), which is the location evidence. The old source is disabled with `superseded_by`. Against 2025 it finds exactly the three Sarajevo vacancies.
- **Brazil:** an open process whose advert is a scanned PDF no longer fails the source. It becomes a review item carrying the process year the embassy names ("Processo seletivo 2026"); a stated recruitment year without a date can never publish itself (`RECRUITMENT_YEAR`). gov.br sends no file date, and the CMS page dates are reused from 2023, so neither is used.
- **Canada:** the Sarajevo office is a consulate under the Budapest embassy; Global Affairs Canada advertises every locally engaged position on the LES portal, which the adapter reads in full. There is no separate channel, so the source is complete.

## The 15 inaccessible sites rechecked (2026-10-03)

Each site was retried with the Windows trust store, certifi and Chrome TLS impersonation (verification always on, challenges never solved).

- **Greece: now a source.** The news list answers Chrome impersonation; job adverts have clear titles ("OGLAS ZA SLOBODNO RADNO MJESTO", "VACANCY ANNOUNCEMENT"). Enabled on `generic` with pagination that stops at the first page without a 2026 item (`stop_at_older_page`). Against 2024 it finds the two known adverts with date, city and deadline. `parse_date` now accepts a leading weekday; the deadline parser reads "submit … by <date>".
- **No local recruitment list (7):** Slovakia, Order of Malta and Ukraine (reachable with impersonation; Ukraine's central page recruits Ukrainian civil servants only), and the Holy See nunciature and the honorary consulates of Cyprus, DR Congo and Bangladesh (no own website or recruitment channel).
- **Awaiting integration (1):** Indonesia. The portal has a public JSON API with the Sarajevo embassy's news (a "CAREER OPPERTUNITY" post in 2023), but it always returns 200 items without paging, so completeness is unproven.
- **Still unavailable (6):** Malaysia, Pakistan and Qatar send incomplete certificate chains (a server fault that the deployment network will not change); Romania and Russia answer with JavaScript browser checks and Kuwait with a Cloudflare challenge, even under impersonation.

## UNDP consultant notices and Indonesia (2026-10-03)

- **UNDP:** new `undpnotices` adapter. One POST to procurement-notices.undp.org/search.cfm with `cur_notice_id=UNDP-BIH` returns every UNDP BiH notice of the year (169: 65 IC, the rest RFQ/RFP/ITB). Open "IC - Individual contractor" rows are kept; each notice page adds country and duration. `adapter_config.opportunity_type` marks them as consultancies (titles such as "GEF8-Flora Expert …" do not say so). First run: 8 open notices, all published.
- **Indonesia:** new `kemlu` adapter on the portal's public `/contentMenu` API (the call the JavaScript site makes, with array slugs `slug[]=sarajevo&slug[]=<section>`). Each section reports `meta.filtered`, which every scan must reach, so the list is provably complete. It reads the embassy's dedicated Karir (Career) section in full and News for career titles. News holds 195 items (`meta.total` 200), so the earlier 200-item response was complete after all; a 2023 dry run finds the "CAREER OPPERTUNITY" post. No advert in 2026.

## Job pages, requirements, reports and languages (2026-10-03)

- Every published job has a page (`/jobs/<id>/<slug>/`) with requirements read from its text by rules in `board/requirements.py`, each shown with the quote it came from. The board filters by education, experience and field of study. Locally, 23 of the 32 stored jobs have requirements; UNDP procurement notices have none, because theirs are in the attached ToR documents.
- Requirement extraction skips degrees listed under "Desirable qualifications" (EUFOR's Purchasing Administrator requires a junior college, which has no level, so it shows no minimum). The asset/required check for languages and the driving licence was broken in the first commit (a word boundary stored as a control character); it is fixed and tested.
- Visitor problem reports: `/report/` and on each job page, listed in admin under *Prijave*. Not e-mailed yet: neither `ADMINS` nor an e-mail backend is configured.
- English interface at `/en/` (owner request); Bosnian stays at `/`.
- Advert translations come from the local `/translate-jobs` skill (owner decision: Claude Code subscription, no API key) through `export_translations`/`import_translations`. One job is translated locally (EUFOR Purchasing Administrator, id 6); the other 22 public jobs are pending. Database backups: `backups/db-before-requirements-*.sqlite3`, `backups/db-before-first-translation-*.sqlite3`.

## Design system Phase 1 (2026-10-03)

- The [design proposal](docs/design/design-system.html) contains an audit, tokens, component specs and redesigned screens. Phase 1 is applied: `board/static/board/tokens.css` is linked before `site.css`, which now has no raw hex values.
- Under 760px the header has two rows: brand and BS/EN on the first, the Oglasi/Izvori tabs on the second. The language switch moved out of `<nav>`. Checked in Chromium: no page (`/`, `/en/`, `/sources/`, a job page, `/report/`) scrolls sideways at 320, 360 or 390px; before the change every page was 35px too wide at 390px.
- Also in Phase 1: a `:focus-visible` outline, input borders at 3.66:1, a violet "review" pill on `/sources/` (it was the same amber as "unavailable") and an SVG sprite (`templates/board/_icons.html`) replacing 📍, ↗ and ◎. No translatable strings changed.
- Dark mode is defined in the tokens but off; it applies only on `<html data-theme="auto">`.
- Tests: 216 discovered locally on Python 3.11, 215 passed, one PostgreSQL-only skip; Django checks and migration drift are clean.

## Design system Phase 2 (2026-10-03)

- Job list: one search row (search, city, type, "Filteri", "Traži"). Organisation, position, education, experience and field sit in a panel opened by a `<details>` summary; the panel is a sibling of the details element (`.more-filters[open]~.filter-panel`), so its fields always submit with the form. It opens by default and shows a count when any of those five is active.
- Active filters show as chips (`views.filter_chips`), each a link to the same results without that parameter; sort is kept. Sort is two links (`views.sort_links`), not a select, so it needs no JavaScript.
- Trust strip (`views.trust_strip`): visible jobs, enabled verified sources with a successful run, and the latest successful check.
- Job card v2: the title link is stretched over the card; "Detalji i uslovi" and "Provjereno" are gone from the card (the job page still has "Provjereno"). Tags are capped at three plus "+n".
- `{% deadline job variant %}` (`board_extras.py`, `_deadline.html`): red for today/tomorrow, amber within 7 days, grey later; Bosnian count agreement via `text.plural`. A job page that is no longer current gets no countdown.
- Job page under 960px: a key-facts grid under the title and a fixed apply bar (`scroll-padding-bottom` set on pages with the bar); the aside's apply button is hidden there.
- Fonts are self-hosted in `board/static/board/fonts/` (OFL); Google Fonts is no longer loaded.
- Checked in Chromium: no sideways scroll at 320, 360 or 390px on `/`, `/en/`, a filtered list and a job page. Tests: 219, all pass (one PostgreSQL-only skip).

## Design system Phase 3 (2026-10-03)

- `/sources/`: rows are grouped by state (with jobs, in review, without jobs, partial, unavailable, awaiting integration, not checked, not found). The four stat cards (Praćeni, Djelimični, Nedostupni, Nisu praćeni) are the filters (`?status=covered|partial|unavailable|untracked`); exact states still work (`?status=empty`) and are what each group's "Prikaži sve (n)" link uses. The full list shows five rows per group. A stacked coverage bar, a name search (`?q=`, case- and diacritic-insensitive) and the status legend in a `<details>` replace the nine filter pills. At 1280px the page is 3,135px long (measured), down from about 9,500px.
- Dark mode is on (`<html data-theme="auto">`, `color-scheme`). An automated WCAG AA text-contrast check on `/`, a filtered list, two job pages, `/sources/` and `/report/` found no failures in either theme. No sideways scroll at 320, 360 or 800px.
- Forced colours: borders on pills, deadline chips, tags, chips and monograms, and system colours for the coverage bar. Not tried in Windows High Contrast mode itself.
- Monograms: new `Organization.short_name` (migration 0034), filled in `data/source_registry.json` (acronyms for organisations, ISO country codes for missions) and imported by `import_registry`. Syndicated jobs use their employer's registry entry when it exists, otherwise an acronym or initials from the name (`text.monogram`). Applied locally: `import_registry` run after backup `backups/db-before-short-names-*.sqlite3`.
- Share images: `/jobs/<id>/share.png` (and `/en/…`) draws a 1200×630 PNG with Pillow (new dependency, `pillow==11.3.0`) from full Public Sans TTFs in `board/og_fonts/`. Only current jobs get the `og:image` tags. Images are cached for a day in the Django cache (local memory per process).
- Usability check: not run; it needs five real participants. Script: [docs/design/usability-check.md](docs/design/usability-check.md).
- The Design canvas Rollout board was not updated or republished.
- Tests: 228, all pass locally (one PostgreSQL-only skip); migration drift is clean.

## Blocked sources, second pass (2026-10-03 afternoon)

Owner approval: complete incomplete certificate chains the way browsers do. Challenge solving and disabled verification remain off-limits. The owner added Claude Code allow rules for `scripts/cert_chain.py` and `scripts/telegram_probe.py`, which the auto-mode classifier otherwise denied. Database backups: `backups/db-before-p0-sources-*.sqlite3`, `backups/db-before-aia-sources-*.sqlite3`.

- **Incomplete chains (AIA):** `scripts/cert_chain.py HOST` reads the served leaf, downloads the missing intermediate from the leaf's "CA Issuers" URL, refuses any self-signed certificate, and proves the chain with a real handshake (certifi roots, hostname check, partial chains off). `--save` stores the intermediate in `data/intermediates/HOST.pem`; sources opt in with `adapter_config.intermediates`, which adds the file to the system trust store context with partial chains off (`ingest.tls_context`). If a site changes CA, the source fails until the script is rerun.
- **Malaysia: now a source.** The embassy's Notice > Job Vacancy page (`generic`, `div.ck-content`, empty note "There are no job vacancies at this time"). The old archive row is superseded.
- **Pakistan: now a source.** The embassy's "Work With Us" page (`#print-section`, "not currently hiring"). The FortiWeb firewall rejects a bot user agent, so the source sends a Chrome one (`adapter_config.browser_user_agent`, plain httpx). The central Vacancies page lists posts in Pakistan only.
- **Qatar: no local recruitment list.** Readable with the chain completed; the site and site map have no jobs or careers section.
- **Russia: no local recruitment list.** sarajevo.mid.ru still answers with a JavaScript check. The embassy's official Telegram channel (t.me/s/RusEmbBiH, about 4,800 posts since 2022) has no vacancy post for any Russian, Bosnian or Serbian job term (`scripts/telegram_probe.py`).
- **Romania: still unavailable.** cariera.mae.ro (chain completed) is a login-only competition platform; www.mae.ro has the same 503 JavaScript check as the embassy site.
- **UNICEF: still blocked.** After a cool-down the listing answered under impersonation, but the second detail page, 5 s later, was challenged (HTTP 202), then the listing too. `adapter_config.request_delay` (a pause before each detail page) was added and stays in the registry config; retry from the server IP.
- **UK:** unchanged (FCDO "Quick Check").
- **Kuwait: no local recruitment list.** The owner checked by hand: the embassy in BiH has no website and the Kuwaiti MFA publishes no vacancies. mofa.gov.kw still sends a Cloudflare challenge to automated clients.

## Employer pages and related jobs (2026-10-03)

- `/sources/<id>/<slug>/` (and `/en/…`; `/sources/<id>/` redirects) per organization: source status with the recruitment audit note and evidence link, current jobs, then past jobs (20 per page, plain text because closed jobs answer 410). Linked from `/sources/`, the employer line of job cards and the job page.
- A job belongs to its registry employer, also when it came through an aggregator (`related.owner`); an unknown employer's job stays on the aggregator's page.
- Past jobs need `Job.published_at` (migration 0035, set by `Job.save` and the bulk publish action). The migration backfills published jobs, and closed jobs closed by the source with no review reason. A job closed by a reviewer (`manual`) or never published is not listed. A past aggregator copy of an own job is left out.
- A page is indexed and in the sitemap only when it lists a current or past job (`views.public_organizations`); others get `noindex`.
- Job page: "Drugi oglasi istog poslodavca" (up to 3, by employer key) and "Slične pozicije" (up to 3, other employers, `board/related.py`). Both sections are left out when empty. Similarity is rule-based: shared title stems (6 letters, advertising noise removed) score 3, job-family words 1, shared fields of study 2 each (max 2), and the same type and education level 1 each. A shared work word is required and the threshold is 4. On the 23 current jobs only the three EU4People/IDC programme jobs get suggestions; fields alone matched unrelated posts and were dropped as a sufficient signal.
- Checked in Chromium (dark theme) on the UNICEF page and job 19; no sideways scroll at the tested width. Phone widths were not re-measured (the resize tool failed).

## Archive backfill of 2025 and ended 2026 adverts (2026-10-03)

- Owner request: past adverts on the employer pages. The daily scrape drops an advert that is already expired when first seen, so before this only jobs caught while open were stored.
- All 52 enabled sources were probed for 2025 and 2026 (discovery only, nothing written). Recruitment portals (Oracle, Workday, Taleo, Avature, CSOD, SuccessFactors, BambooHR, Lanteria, PeopleSoft, ERA, UN Careers, Canada), Impactpool and the current-list pages (OSCE, OHR, RCC, EUFOR, UNCT, Ireland, Denmark, Japan, Malaysia, Pakistan) show open adverts only. ReliefWeb keeps expired jobs only in its API, which asks for an approved app name; none is configured. Italy's concluded list has nothing for 2025 and its 2026 advert was already stored. Slovenia's full MFA list runs past the page limit and a Sarajevo advert is rare, so it was left out. Germany's sitemap would need a lower article floor and its last adverts are from 2020/2022.
- `manage.py scrape_jobs --history YEAR [--source ID]` (`ingest.archive_source`) runs only sources whose `adapter_config` has a `history` object (12 in the registry); its keys override the daily settings for the run. It stores ended adverts of that year as `closed`/`archive` (migration 0036), never touches a known URL, and leaves open adverts to the daily scrape. An advert that passes every publication check except its deadline gets `published_at`, so the employer page lists it; the others keep their reason in `field_evidence.review_reason`.
- Adapter changes in archive mode: RAI keeps the table's closed rows of the year (not cancelled ones); WordPress reads only that year and takes `search` (GIZ's history adds mreza-mira.net's Arhiva with `search=GIZ`, 15 posts instead of 1,145); UNDP notices searches the year's posting dates and keeps ended IC notices, 3 s apart (owner approved the ~150 page fetches, 2026-10-03).
- Past jobs on employer pages are now ordered by deadline, newest first, since backfilled jobs were first seen long after they ended.
- Run locally: 2026 — 65 archived, 63 listed (UNDP 57, EEAS 4, Spain 1, RAI 1); 2025 — 113 archived, 109 listed (UNDP 95, EEAS 8, GIZ 3, RYCO 2, RAI 1). Not listed: Swiss Political Advisor 2025 (no publication date in the PDF), RAI Organisational Expert, Director of Secretariat, Research and Mentorship Coordinator and the HR review call (titles fail the job-advert check), and a second RYCO copy of the Finance and Administration advert. Database backup: `backups/db-before-archive-backfill-20261003-213720.sqlite3`.
- The Hetzner database was migrated and the registry imported on 2026-10-07. Its 2026 history pass stored 67 archived adverts, 65 listed on employer pages; the 2025 pass stored 113 archived adverts, 109 listed. Sweden's archive page returned 403 in both passes; Greece returned 403 in the 2026 archive pass but worked in the daily scrape and the 2025 archive pass.

## Hetzner deployment (2026-10-07)

- Public site: https://poslovi.aneskurtovic.com/ via Caddy with HTTPS, HTTP redirect and a one-hour HSTS policy. The homepage, coverage page, feed, sitemap, robots file and `/health/` returned 200. `/health/scrape/` returns 503 for the affected sources below.
- `compose.prod.yaml` runs web and daily scraper containers on Hetzner. Both use a dedicated `diplomacyjobs` database and role inside the **existing** `ludo-postgres` PostgreSQL 16 container; there is no separate production PostgreSQL container. The scraper runs daily at 06:00 Sarajevo time.
- [Woodpecker pipeline #1](https://ci.aneskurtovic.com/repos/7/pipeline/1) launched the site at commit `319aa59`; [pipeline #3](https://ci.aneskurtovic.com/repos/7/pipeline/3) later deployed the editorial queue and duplicate reconciliation at `9d2b116`. Both ran the SQLite and PostgreSQL Django tests. The restricted SSH deployment command takes a checked database dump before rebuilding and restarting the app.
- The first full server scrape completed: 49 of 52 enabled sources succeeded, producing 21 published jobs and eight Impactpool copies needing review. Slovenia and Germany worked from the server. Sweden (#26) returned 403, UN Careers (#51) returned 504 from its API, and ReliefWeb (#53) returned an HTTP 202 challenge. The sources page marks these unavailable; they are not treated as zero vacancies. A browser TLS fingerprint also received 504 from the UN Careers API. [ReliefWeb's official API requires a pre-approved appname](https://apidoc.reliefweb.int/parameters); none is configured, while the older HTML approach previously worked without one.
- `/editor/` now handles uncertain listings with source evidence, corrections and guarded publish/reject actions. `reconcile_duplicates` closed the eight Impactpool copies as `duplicate`, leaving the editorial queue empty. Each scheduled scrape runs this reconciliation.
- A custom-format PostgreSQL dump was restored successfully into a temporary database and the temporary database removed. [The backup cron file](deploy/diplomacyjobs-backup.cron) is installed on the host and runs daily with 30-day retention.

## Error pages and screenshot review (2026-10-07)

- **Error pages:** `templates/404.html`, `400.html`, `403.html`, `403_csrf.html` and the closed-job page (`board/job_gone.html`, 410) extend `board/error.html`: an "Error 404"-style eyebrow, a headline set like the board's hero, and two actions that sit side by side on desktop and stack full width under 760px. All are `noindex` and follow the URL's language. `500.html` repeats the layout without `base.html`, because Django renders it without a request or context processors; it links by path (`/` or `/en/`). The CSRF page offers "Otvori obrazac ponovo".
- `views.public_base` returns an empty origin instead of raising when the Host header is rejected, so the 400 page for a bad host cannot turn into a 500.
- **Screenshot review:** every public page (job list, filters open, job page, `/sources/`, an employer page, `/report/`, `/en/`) was captured at 390px and 1280px in light and dark, first on the live site, then locally against a fresh scrape (26 published jobs), plus 768px for the job page and list. No page scrolls sideways at any width. Fixed: phone job cards put the countdown under the date with the official link beside it (one row shorter per card); under 960px the job page's side summary drops location, deadline and type, which the key-facts grid already shows (`.in-key-facts`); the phone sources table wraps the city and source-discovery date under their value instead of squeezing them or running off the card; report-form fields use the site surface colours in dark mode, and radios are drawn in the brand colour with 44px rows on phones (native in forced-colours mode).
- **Phone job list (`d942b9c`):** the search box takes two rows (search and Traži, then city, type and an icon-only Filteri that keeps its count and accessible label), sort and an icon-only feed link share a row, and the headline is 25px; the first job starts at 488px of an 844px screen instead of 602px (measured on the live site). Under 375px the search button widens and select padding tightens; select text stays 16px so iOS does not zoom on focus (at 320px "Svi gradovi" loses its last letter). The "+n" tag chip stays with the last tag, the report page's back link uses the shared icon, and error pages mark no tab as current.
- **CI failure and fix:** with `400.html` present, `ProductionHostTests` rendered the site layout, whose `{% static %}` links need the collected manifest; CI never runs `collectstatic`, so the test raised "Missing staticfiles manifest entry". The test now uses plain static storage like the other page tests. Production builds collect static files in the Dockerfile and were not affected, but nothing after `6ddeef0` deployed until `ca941e3`.

## Installable site and htmx filters (2026-10-07 evening)

- **Installable site:** `/manifest.webmanifest` (standalone, brand blue, 192/512 and maskable icons from `scripts/make_icons.py` in `board/static/board/icons/`) and a service worker at `/sw.js` (template `templates/board/sw.js`, `Cache-Control: no-cache`, registered by `register-sw.js`). It precaches the offline pages, stylesheets, the main font and an icon under a version derived from the hashed static names; `/static/` is cache-first, and page navigations are network-first. Job pages and the two home pages (not report forms, not filtered lists) are kept in `dj-pages-v1`, at most 20, for offline reading. When offline, any other page shows `/offline/` or `/en/offline/`. Admin, editor, health and feed are never touched.
- **htmx job list:** htmx 2.0.4 is self-hosted (`board/static/board/htmx.min.js`). The form (`_search_form.html`) updates `#results` (`_results.html`) on select change, typing (500 ms), and submit, and pushes a clean URL with empty parameters dropped. Chips, "Poništi sve", sort and page links are boosted and also swap the form out of band, so its fields match the URL. A hidden `role="status"` paragraph announces the result count. The view returns the partial for `HX-Request` (but not history restore) and sets `Vary` on the htmx headers. Without JavaScript, the plain GET form and links work as before. The form and the boosted links share one `hx-sync` scope on `#results`. Without it, tapping a chip right after typing raced the search box's own request and restored the old results.
- **Checked in Chromium** (local SQLite copy, 390 and 1280px, light and dark): search, city, sort, chips, back button, the service worker taking control, and offline after stopping the server. The cached job page and the cached home page opened; `/sources/` showed the offline page in the URL's language. Playwright's `set_offline` does not cut off service-worker fetches in Chromium, so stop the server to test offline. Not yet checked on a real phone (install prompt, iOS home screen).
- **CI:** the GitHub Actions workflow briefly moved to Node 24 action versions; it was removed the same day (see below).

## Next steps

1. Recheck Sweden and UN Careers access from Hetzner (a `source-scout` subagent per source); investigate an approved access path for ReliefWeb if that feed remains important. Do not solve JavaScript challenges. Romania, UK and UNICEF remain unavailable; retry at the 90-day audit. Rerun `scripts/cert_chain.py HOST --save` if Malaysia or Pakistan fails on TLS.
2. When the owner asks, run `/translate-jobs` (Haiku translator subagents) for the 21 public jobs awaiting translations. Translation is on demand only.
3. After this push deploys, check on a real phone that the site installs (Android Chrome prompt, iOS "Add to Home Screen") and that a job page opened earlier still opens offline.
4. App track: optional push notifications for a saved search. Other htmx candidates are "load more" instead of page links and sending the report form in place.
5. **Usability check** (Design Phase 3, item 6) with five job seekers on mobile: [script](docs/design/usability-check.md). Check the share image preview in Viber/WhatsApp at the public URL.

## Design system files

- `docs/design/design-system.html`: the full proposal (audit, principles, tokens, components, screens, rollout). Open it locally in a browser; it reads `board/static/board/tokens.css`.
- `board/static/board/tokens.css`: the live tokens; `site.css` uses only its alias tokens.
- `docs/design/canvas/project/`: source of the 9-board Design canvas at https://claude.ai/artifact/2sbsjQcyQhKx6VimewJzoN (private to the owner): `canvas.json` (index and layout) plus Overview (`Main`), Audit, Foundations, Components, Rollout, JobList, JobListMobile, JobPageMobile and Sources `.dc.html` boards. To change the canvas, edit these files and republish them to that URL, then commit.
- `docs/design/before/`: screenshots of the site before Phase 1.
- The proposal applied skills from the Designer Skills pack. To use them as skills in a local Claude Code session, run `/plugin marketplace add Owl-Listener/designer-skills`, then install design-systems, ui-design, visual-critique, prototyping-testing, interaction-design and ux-strategy from `/plugin`.

## Working notes

- CI and production target Python 3.12. Set `DJANGO_DEBUG=1` before local management commands, and use a Python 3.12 environment with `requirements.lock` for parity. Verification commands are in README.
- The local dev server runs on http://127.0.0.1:8000/ with `DJANGO_DEBUG=1`. On Windows the venv launcher can leave the serving child process alive; stop both before restarting, and check process identity rather than reusing old PIDs.
- `import_registry` preserves existing enablement, status and timestamps; enable or disable sources in admin. `scripts/validate_recruitment_integrations.py` runs read-only live checks (`--adapter NAME` for one).
- In the 2026-10-03 local run, the German sitemap source failed TLS because the Windows certificate store lacked ISRG Root X2. It passed from the Hetzner server.
- Source access policy: TLS verification stays on, JavaScript challenges are never solved, and Chrome TLS impersonation is opt-in per source (`adapter_config.impersonate`).
- Local database backups made before each data change are in ignored `backups/`.
- CI has no collected static files. Any test that renders a page, including an error page (400/403/404/500), needs plain static storage (`PLAIN_STATIC` in `test_i18n.py`/`test_requirements.py`, or the same `STORAGES` override); otherwise it passes locally where `staticfiles/` exists and fails in CI. To reproduce CI, move `staticfiles/` aside before running the suite.
- Page screenshots: Playwright with the preinstalled Chromium, at 390px (mobile, touch) and 1280px, `colorScheme` light and dark, full-page. To see error pages, run with `DJANGO_DEBUG=0`, a SQLite copy of the database, `collectstatic` and a server restart after each CSS change (the manifest is read at startup).
- Unreachable commit `eb52b78` holds an obsolete SQLite-only workflow; do not restore it.

## History

Detailed evidence for earlier work lives in the dated docs and git history:

- 2026-10-02: reliability work and Linux CI ([run 37071234992](https://github.com/aneskurtovic/DiplomacyJobs/actions/runs/37071234992)); 30 complete sources live-checked.
- 2026-10-03: [46-entry discovery audit](docs/source-audit-2026-10-03.md) (`e19a79a`); [seven recruitment integrations](docs/recruitment-integrations-2026-10-03.md) (`7898c82`); cross-source deduplication (`0fe72e3`); [aggregators](docs/aggregator-integrations.md) (`6acca61`); [INGO employer check](docs/ngo-donor-employers-2026-10-03.md) and Save the Children/CRS (`3802aad`); bulk-publish guard and admin history, RYCO Tirana job closed as `manual` (`8ec1cc8`).

Counts inside the dated docs describe the state on their date, not now.
