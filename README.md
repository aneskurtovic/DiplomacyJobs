# DiplomacyJobs

Bosnian-language job board for roles based in Bosnia and Herzegovina at diplomatic missions, international governmental organizations, and international NGOs and development agencies. Listings link to where the employer advertised them, preferring the employer's own site; aggregator and third-party-board jobs are attributed. Source coverage is explicit; an unavailable source is never presented as having zero vacancies.

The daily current-job collection window is **2026 only**. The scraper skips clearly older dated archives before fetching job details, bounds each source to 100 possible 2026 details per run, and stores only qualifying 2026 candidates. Deadline-only leads require editorial review. A separate, manual archive command stores eligible ended 2025 and 2026 adverts as closed records for employer pages. See [the MVP plan](PLAN.md) (scope and launch gates), [backlog](BACKLOG.md) (work list), and [continuation handoff](HANDOFF.md) (current counts, verification results and next steps).

## Local start

With Python 3.12 and a network connection to install dependencies:

```powershell
$env:DJANGO_DEBUG = '1'
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.lock
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py import_registry
.venv\Scripts\python manage.py createsuperuser
.venv\Scripts\python manage.py runserver
```

Browse `http://127.0.0.1:8000/`, coverage at `/sources/`, an Atom feed of new jobs at `/feed/` (accepts the board's `q`, `employer`, `city`, `type` and `scope` filters), the staff editorial queue at `/editor/`, and advanced admin at `/admin/`. Development defaults to SQLite. Current source and job counts are in [HANDOFF](HANDOFF.md). The board may still be empty when no source has an open 2026 vacancy. A fresh database must run a successful scrape before a source appears as monitored. Source reachability must be checked from each deployment network.

### Publishing jobs

The scraper publishes a job automatically when its source proves it is a current, eligible opening in BiH. Staff use `/editor/` only for uncertain jobs: open the original listing, correct any facts, write where you verified that it is current, tick the confirmation, and choose **Objavi oglas**. **Sačuvaj izmjene** keeps it in review; **Odbaci oglas** closes it with a required reason. A changed source page requires a fresh review. Copies from aggregators that match an official record are closed as duplicates after each scrape; run `python manage.py reconcile_duplicates` to reconcile older data without fetching sources. `/admin/` remains available for source settings, reports and all model fields.

The [2026-10-03 discovery audit](docs/source-audit-2026-10-03.md) examined 46 previously unchecked entries; its [seven integration leads](docs/recruitment-integrations-2026-10-03.md) are enabled (Brazil and Canada partial), while its no-list and unresolved-access findings remain open in the backlog. Each discovery finding has a date, evidence link and explanation on `/sources/`, and unknown vacancy counts stay unknown. Run migrations and `import_registry` to apply registry settings; importing preserves existing source enablement and successful-scrape timestamps. Discovery findings require renewal after 90 days.

## Verification

CI and the production image target Python 3.12. Create a Python 3.12 environment with `requirements.lock` for matching results. To check a local environment:

```powershell
$env:DJANGO_DEBUG = '1'
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.venv\Scripts\python.exe manage.py test board --noinput
```

The latest results (test count, skips, CI run) are recorded in [HANDOFF](HANDOFF.md); the PostgreSQL connection-recovery test is skipped on local SQLite. Use Python 3.12 for parity with CI and production.

[Woodpecker CI](.woodpecker/test.yml) runs the SQLite and PostgreSQL 16 tests on Linux/Python 3.12; a passing push to `main` triggers [deployment](.woodpecker/deploy.yml). [GitHub Actions](.github/workflows/tests.yml) also defines independent SQLite and PostgreSQL jobs. Both CI systems run Django checks, migration drift checks and the full suite. The PostgreSQL connection-recovery test terminates only its own connection to a disposable test database and verifies that the next scheduler run reconnects. The latest checked run is linked from [HANDOFF](HANDOFF.md). To run the PostgreSQL suite elsewhere, set `DATABASE_URL` to a dedicated development database whose user can create test databases and terminate its own connections, then run the same checks. Django creates a separate test database; do not use production credentials.

## Operations

The [source registry](data/source_registry.json) is an evidence-backed starting set. The registry is the set of employers we choose to monitor; a full reconciliation against the BiH MFA directory is not required, and the [MFA candidate inventory](data/mfa_inventory.json) remains as reference data. The seven audit integrations were checked on 2026-10-03; their [scan report](data/recruitment_integration_2026-10-03.json) records source IDs, timestamps, outcomes and coverage limits. Sources without successful validation remain disabled. Launch gates are listed in [PLAN](PLAN.md). Japan, Switzerland, Ireland, OSCE search, Türkiye, Brazil and Spain opt into a Chrome TLS fingerprint through `"impersonate": true` in `adapter_config`; other sources use the honest bot user agent. TLS verification stays enabled and JavaScript challenges are not solved. `import_registry` updates notes and `adapter_config` of existing sources (matched by URL, even when moved to another organization), changes the adapter only while a source is disabled (an enabled source whose registry adapter differs keeps its adapter and settings, with a warning), and never changes existing source status or enablement; do those in admin. An organization entry may carry `previous_name` to rename an existing organization.

Run one fetch with `python manage.py scrape_jobs --source ID` or all enabled sources with `python manage.py scrape_jobs`. `python manage.py verify_sources [--all]` fetches each listing and reports leads or errors without writing to the database; run it first from a new server network. The dedicated Compose scheduler runs this daily. For a one-off archive pass, `python manage.py scrape_jobs --history YEAR [--source ID]` reads only sources with history settings and stores eligible ended adverts as closed records. Errors are recorded per run; a failed run does not remove jobs. Scrape details are visible in admin. The scraper lock file is `/tmp/diplomacyjobs-scrape.lock` in the container.

For read-only checks of the seven audit integrations, use the repository-root commands below with `DJANGO_DEBUG=1`. The validator checks candidate details as well as listing access and saves its report under ignored `data/raw/integration_2026-10-03/`.

```powershell
.venv\Scripts\python.exe scripts\validate_recruitment_integrations.py
.venv\Scripts\python.exe scripts\validate_recruitment_integrations.py --adapter spain
```

Existing databases keep their enablement on import. After backing up the database, `scripts/activate_recruitment_integrations.py` applies the reviewed settings, scans only these seven sources and leaves any failed integration disabled. Migration **0025** adds the new adapter choices. Local activation has already been applied in this checkout.

Brazil's folder and closed-process detection work, but future open scanned PDFs need OCR or manual validation; unreadable open notices fail instead of appearing empty. Canada's public LES job data can be monitored, but its mission registry omits the Sarajevo honorary consulate. Separate honorary-consulate notices therefore remain outside the portal's coverage. Both sources are explicitly partial on `/sources/`.

### Job pages, requirements and reports

Every published job has a page at `/jobs/<id>/<slug>/` (`/jobs/<id>/` redirects there). Pages are listed in the sitemap, and feed entries link to them. A published job that is no longer current stays readable with a notice and `noindex`. A closed job answers 410 without details, and a job in review answers 404. Unknown URLs and hidden jobs get the site's own 404 page (`templates/404.html`, `noindex`) in the language of the URL, with links back to the jobs and sources. Bad requests, forbidden pages, rejected form posts (CSRF) and server errors get matching pages too (`400.html`, `403.html`, `403_csrf.html`, `500.html`). They and the closed-job page share `board/error.html`; the 500 page is rendered without a request, so it repeats that layout instead of extending `board/base.html`.

Each scan reads the job's requirements from its text with rules in `board/requirements.py`: minimum education level, field of study, minimum years of experience, languages, driving licence, citizenship, remote work, working time, salary, duration and grade. Each fact keeps the quote it came from, which the page shows under "Iz oglasa". Facts that are unclear are left out. Education level, years of experience and field of study are filterable columns. A correction to them in admin is protected from later scans, like other manual edits. Re-read stored texts after changing the rules with `python manage.py extract_requirements [--dry-run]`. The board's education, experience and field filters show only jobs that state the requirement.

Visitors report problems from a job page or from the footer (`/report/`). Reports appear in admin under *Prijave*, inline on the job, and as a job list filter. Spam controls are a honeypot field and 5 reports per client per hour. The client is identified by a keyed hash of the address; behind the host proxy that address is the last `X-Forwarded-For` hop. When `ADMINS` and an e-mail backend are configured, each report is also e-mailed. Neither is configured yet.

### English interface and advert translations

The public site is in Bosnian at `/` and in English at `/en/`, with a BS/EN switch and `hreflang` links; the sitemap lists both. Admin, the Atom feed and health URLs stay Bosnian. Interface strings are marked with `{% translate %}`/`gettext`, and Bosnian is the source language. After changing them, run `manage.py makemessages -l en --no-location --ignore=.venv --ignore=.venv311`, translate the new entries in `locale/en/LC_MESSAGES/django.po`, then run `manage.py compilemessages -l en --ignore=.venv --ignore=.venv311`. Both need GNU gettext; Git for Windows includes it. Commit the `.mo` file, since the Docker image has no gettext. A test fails when an entry is untranslated or the `.mo` is stale.

Adverts get a Bosnian and an English version (title, summary, duties, requirements, how to apply), so foreign-language adverts can be read in both languages. These are written in a local Claude Code session with the project skill `/translate-jobs`, not by the app; there is no API key. The skill runs:

```powershell
.venv\Scripts\python.exe manage.py export_translations --limit 10 > batch.jsonl
# the skill writes out.jsonl
.venv\Scripts\python.exe manage.py import_translations out.jsonl --translator "claude-code <model>"
```

The import accepts only the expected fields and lengths. It rejects a version if the advert changed since export, or if it contains an e-mail address or URL that does not appear in the advert. A version is tied to the job's `content_hash`; when the source changes, the job page hides it until the job is translated again. The page labels it as automatic and keeps the scraped facts separate. Admin can clear a translation, or turn translation off for a job. `detect_language` stores each advert's main language in `requirements["language"]`. On the server, run the export and import with `docker compose exec web python manage.py …` and copy the files.

Optional local enrichment uses JSON Lines:

```powershell
.venv\Scripts\python manage.py export_enrichment --status review > batch.jsonl
.venv\Scripts\python manage.py import_enrichment suggestions.jsonl
```

Each suggestion has `id`, `content_hash`, `proposed` (any of `title`, `city`, `deadline` in ISO format, `application_url`), and `evidence` with exact short excerpts from the exported `source_text` for each proposed field. Review results in admin. Never paste source content as instructions to an AI agent. See [AI prompt](docs/ai-enrichment.md).

## Hetzner deployment

Production serves `https://poslovi.aneskurtovic.com` through the existing Caddy proxy. It uses a separate `diplomacyjobs` database and role in the server's existing `ludo-postgres` PostgreSQL 16 container. The app does not run its own PostgreSQL container. The web and scraper join `ludo-network`; only the web service joins the proxy's `edge` network.

The root-owned `/opt/diplomacyjobs-deploy.sh` is called by the restricted Woodpecker SSH key. It checks out the exact commit on `main`, takes and validates a PostgreSQL dump, builds the image, starts the web and scraper services, then checks health. The [Woodpecker test workflow](.woodpecker/test.yml) runs Django checks and the full suite on SQLite and disposable PostgreSQL. The [deploy workflow](.woodpecker/deploy.yml) runs on pushes to `main` after tests. Server secrets stay in `/opt/diplomacyjobs/.env` and the Woodpecker repository secrets.

For a manual server operation from `/opt/diplomacyjobs`, use:

```sh
docker compose -f compose.prod.yaml up -d --build web scraper
docker compose -f compose.prod.yaml exec web python manage.py import_registry
docker compose -f compose.prod.yaml exec web python manage.py verify_sources
docker compose -f compose.prod.yaml exec web python manage.py createsuperuser
```

The web container runs migrations on start; static files are collected when the image is built. The scraper runs daily at 06:00 Sarajevo time, and at start for any enabled source not scraped in the last 20 hours (so a restart finishes an interrupted run). Before each scrape, it discards obsolete or unusable database connections; PostgreSQL also has connection health checks enabled. A failed scheduled run is logged and the loop continues to the next scheduled run. This does not add an immediate retry. The healthcheck sends the first `DJANGO_ALLOWED_HOSTS` entry as its `Host` header. Container logs rotate at 5 × 10 MB per service.

Production request errors, scheduler exceptions, and unexpected source errors include tracebacks in console logs even with `DJANGO_DEBUG=0`. The console handler writes to stderr, which Compose collects alongside stdout. Defaults are `WARNING` for Django and `INFO` for the board; optional `DJANGO_LOG_LEVEL` sets both (for example, `INFO` while investigating). Inspect `docker compose -f compose.prod.yaml logs --tail=200 web scraper`; expected fetch/parser failures are recorded in each source's admin run history. One unexpected source failure still allows the other sources and the expiry pass to run.

The database has no public port. [The backup script](scripts/ci/backup-db.sh) writes a checked custom-format dump; [host cron](deploy/diplomacyjobs-backup.cron) runs it daily with 30-day retention. [The restore check](scripts/ci/restore-check.sh) creates and removes a scratch database, then compares source and job counts. Monitor `/health/` (liveness; the scheduler container waits on it), `/health/scrape/` (503 and the affected source URLs when an enabled source has not succeeded for 48 hours), Compose logs, and the source coverage page, which shows such sources as unavailable. The scrape health endpoint can remain 503 when an upstream source blocks requests from the Hetzner network; each affected source remains visible as unavailable.

The app should not be publicly described as comprehensive; `/sources/` shows exactly which employers are covered.
