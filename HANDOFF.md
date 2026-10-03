# DiplomacyJobs continuation handoff

Updated: 2026-10-03 (Europe/Sarajevo). This is the only file that records current counts and verification results; [PLAN.md](PLAN.md) holds scope and launch gates, [BACKLOG.md](BACKLOG.md) the work list. Nothing has been deployed.

## Current state (verified 2026-10-03, local SQLite)

- **Commit:** see `git log` on `main` (job pages, requirements, reports, English interface and translation import, 2026-10-03). The last CI run checked was [37116293201](https://github.com/aneskurtovic/DiplomacyJobs/actions/runs/37116293201) on `2028a85`; check CI for the newer commits, which add migrations 0032–0033.
- **Tests:** 216 discovered locally: 215 passed, one PostgreSQL-only skip. Django checks and migration drift are clean.
- **Registry:** 87 organizations (41 embassies, 7 consulates, 6 honorary consulates, 28 international organizations, 2 INGOs, 1 development agency, 2 aggregators); 57 sources, **50 enabled**.
- **Coverage on `/sources/`** (87 rows): **50 complete** (45 official mission/IGO sources, 2 INGOs, GIZ via mreza-mira.net and 2 aggregators; 10 with published jobs, 40 empty), **0 partial**, **8 unavailable** (Malaysia, Pakistan, Qatar, Romania, Russia, Kuwait, UK, UNICEF), **30 no local recruitment list**, 0 awaiting integration, 0 unchecked.
- **Jobs:** 23 published (all visible on the board; 8 of them UNDP consultancies from the new notices source), 0 in review, 9 closed. Content review of the original 21 done 2026-10-03; the 8 UNDP notices published automatically under the rule.

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

## Next steps

1. Run `/translate-jobs` for the 22 untranslated public jobs, and again after each scrape that adds jobs.
2. **Deployment:** Hetzner, HTTPS, `verify_sources` from the server, daily scrape, backup restore. Recheck the Windows-store TLS cases (Germany) from the server. Push and CI are not deployment proof.
3. Remaining blocked sites (BACKLOG P0) stay blocked by policy; recheck them with the 90-day audit renewals.

## Working notes

- Use `.venv311` (Python 3.11.3, matches `requirements.lock`); do not rebuild `.venv` (Python 3.14, temp-directory errors). CI and production target Python 3.12. Verification commands are in README.
- The local dev server runs on http://127.0.0.1:8000/ with `DJANGO_DEBUG=1`. On Windows the venv launcher can leave the serving child process alive; stop both before restarting, and check process identity rather than reusing old PIDs.
- `import_registry` preserves existing enablement, status and timestamps; enable or disable sources in admin. `scripts/validate_recruitment_integrations.py` runs read-only live checks (`--adapter NAME` for one).
- Locally, the German sitemap source fails TLS: `ssl.create_default_context()` uses the Windows certificate store, which here lacks ISRG Root X2 (diplo.de's Let's Encrypt chain). certifi and standard Linux CA bundles include it; the source passed with certifi as the trust store. Recheck from the server.
- Source access policy: TLS verification stays on, JavaScript challenges are never solved, and Chrome TLS impersonation is opt-in per source (`adapter_config.impersonate`).
- The local `admin` superuser has a deliberately weak, owner-chosen development password. Never copy this database or account to a deployment; create production users with `createsuperuser`.
- Local database backups made before each data change are in ignored `backups/`.
- The GitHub CLI token lacks `workflow` scope; pushes that change `.github/workflows/` need a credential with that scope (earlier pushes used Git Credential Manager).
- Unreachable commit `eb52b78` holds an obsolete SQLite-only workflow; do not restore it.

## History

Detailed evidence for earlier work lives in the dated docs and git history:

- 2026-10-02: reliability work and Linux CI ([run 37071234992](https://github.com/aneskurtovic/DiplomacyJobs/actions/runs/37071234992)); 30 complete sources live-checked.
- 2026-10-03: [46-entry discovery audit](docs/source-audit-2026-10-03.md) (`e19a79a`); [seven recruitment integrations](docs/recruitment-integrations-2026-10-03.md) (`7898c82`); cross-source deduplication (`0fe72e3`); [aggregators](docs/aggregator-integrations.md) (`6acca61`); [INGO employer check](docs/ngo-donor-employers-2026-10-03.md) and Save the Children/CRS (`3802aad`); bulk-publish guard and admin history, RYCO Tirana job closed as `manual` (`8ec1cc8`).

Counts inside the dated docs describe the state on their date, not now.
