# DiplomacyJobs

Bosnian-language job board for roles in diplomatic missions and international governmental organizations based in Bosnia and Herzegovina. Listings link to official employers. Source coverage is explicit; an unavailable source is never presented as having zero vacancies.

The current collection window is **2026 only**. The scraper skips clearly older dated archives before fetching job details, bounds each source to 100 possible 2026 details per run, and stores only qualifying 2026 candidates. Deadline-only leads require admin review. See [the MVP plan](PLAN.md), [backlog](BACKLOG.md), and [continuation handoff](HANDOFF.md).

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

Browse `http://127.0.0.1:8000/`, coverage at `/sources/`, an Atom feed of new jobs at `/feed/` (accepts the board's `q`, `employer`, `city`, `type` and `scope` filters), and admin at `/admin/`. Development defaults to SQLite. The verified local snapshot on **2026-10-03** has **39 enabled sources: 35 complete and four partial** (Sweden, RYCO, Brazil and Canada). The board may still be empty when none has an open 2026 vacancy. A fresh database must run a successful scrape before a source appears as monitored. Source reachability must be checked from each deployment network.

The [2026-10-03 discovery audit](docs/source-audit-2026-10-03.md) examined all 46 previously unchecked entries: 23 had no local recruitment list found, seven needed integration, 15 had unresolved access/rendering problems, and one was an obsolete OSCE duplicate. The seven integrations are now enabled locally; the 23 no-list and 15 unresolved findings remain. Each discovery finding has a date, evidence link and explanation on `/sources/`. Unknown vacancy counts remain unknown. Run migrations and `import_registry` to apply registry settings; importing preserves existing source enablement and successful-scrape timestamps. Recruitment discovery is separate from diplomatic-presence verification and successful scraping; discovery findings require renewal after 90 days.

The [seven integration follow-ups](docs/recruitment-integrations-2026-10-03.md) passed first local scrapes: UAE, Türkiye Mostar, Türkiye Sarajevo, Spain and Slovenia have complete listing coverage; Brazil and Canada are partial. Coverage now shows **zero awaiting integration**, 35 complete, four partial, 23 no-list and 17 unavailable sources (the 15 unresolved audit cases plus UK/UNICEF). No current job was imported, and all 15 existing job rows were preserved. These are local results; the integrations have not been deployed.

## Verification

CI and the production image target Python 3.12. This Windows checkout also has an existing `.venv311` (Python 3.11.3) with dependencies matching `requirements.lock`. The following commands passed on 2026-10-03:

```powershell
$env:DJANGO_DEBUG = '1'
$env:TEMP = Join-Path (Get-Location) 'data\raw\test-temp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
.venv311\Scripts\python.exe manage.py check
.venv311\Scripts\python.exe manage.py makemigrations --check --dry-run
.venv311\Scripts\python.exe manage.py test board --noinput
```

The integration verification discovered **154 tests: 153 passed and the PostgreSQL connection-recovery test was skipped on local SQLite**. This includes 19 new adapter regression tests for employer/location filters, currentness, closed processes, pagination, changed layouts and failure-safe preservation of published jobs. `.venv` uses Python 3.14.7 in this checkout; its earlier test run hit temporary-directory permission errors. The writable test directory above avoids that environment issue. Use the verified `.venv311` here or create a Python 3.12 environment with the locked dependencies.

[GitHub Actions](.github/workflows/tests.yml) defines independent SQLite and PostgreSQL 16 jobs on Linux/Python 3.12. Both run Django checks, migration drift checks, and the full suite. The PostgreSQL job also terminates only the test's own connection to the disposable test database and verifies that the next scheduler run reconnects. Historical reliability/audit CI results are recorded in [HANDOFF](HANDOFF.md); the audit gate passed 132 tests on PostgreSQL and 131 with one skip on SQLite. **Linux/PostgreSQL CI has not been run for the seven integration changes.** Neither Docker nor PostgreSQL was available in the recorded local verification. To run the PostgreSQL suite elsewhere, set `DATABASE_URL` to a dedicated development database whose user can create test databases and terminate its own connections, then run the same checks. Django creates a separate test database; do not use production credentials.

## Operations

The [source registry](data/source_registry.json) is an evidence-backed starting set. The [MFA candidate inventory](data/mfa_inventory.json) distinguishes local and nonresident missions. Complete international and honorary-consulate reconciliation before launch. Thirty complete sources were live-checked on 2026-10-02; the five complete and two partial audit integrations were checked separately on 2026-10-03. Their [scan report](data/recruitment_integration_2026-10-03.json) records source IDs, timestamps, outcomes and coverage limits. Sources without successful validation remain disabled. The launch threshold is at least 10 complete working sources, alongside the remaining inventory, CI and deployment gates. Japan, Switzerland, Ireland, OSCE search, Türkiye, Brazil and Spain opt into a Chrome TLS fingerprint through `"impersonate": true` in `adapter_config`; other sources use the honest bot user agent. TLS verification stays enabled and JavaScript challenges are not solved. `import_registry` updates notes and `adapter_config` of existing sources (matched by URL, even when moved to another organization), changes the adapter only while a source is disabled (an enabled source whose registry adapter differs keeps its adapter and settings, with a warning), and never changes existing source status or enablement; do those in admin. An organization entry may carry `previous_name` to rename an existing organization.

Run one fetch with `python manage.py scrape_jobs --source ID` or all enabled sources with `python manage.py scrape_jobs`. `python manage.py verify_sources [--all]` fetches each listing and reports leads or errors without writing to the database; run it first from a new server network. The dedicated Compose scheduler runs this daily. Errors are recorded per run; a failed run does not remove jobs. Scrape details are visible in admin. The scraper lock file is `/tmp/diplomacyjobs-scrape.lock` in the container.

For read-only checks of the seven audit integrations, use the repository-root commands below with `DJANGO_DEBUG=1`. The validator checks candidate details as well as listing access and saves its report under ignored `data/raw/integration_2026-10-03/`.

```powershell
.venv311\Scripts\python.exe scripts\validate_recruitment_integrations.py
.venv311\Scripts\python.exe scripts\validate_recruitment_integrations.py --adapter spain
```

Existing databases keep their enablement on import. After backing up the database, `scripts/activate_recruitment_integrations.py` applies the reviewed settings, scans only these seven sources and leaves any failed integration disabled. Migration **0025** adds the new adapter choices. Local activation has already been applied in this checkout.

Brazil's folder and closed-process detection work, but future open scanned PDFs need OCR or manual validation; unreadable open notices fail instead of appearing empty. Canada's public LES job data can be monitored, but its mission registry omits the Sarajevo honorary consulate. Separate honorary-consulate notices therefore remain outside the portal's coverage. Both sources are explicitly partial on `/sources/`.

Optional local enrichment uses JSON Lines:

```powershell
.venv\Scripts\python manage.py export_enrichment --status review > batch.jsonl
.venv\Scripts\python manage.py import_enrichment suggestions.jsonl
```

Each suggestion has `id`, `content_hash`, `proposed` (any of `title`, `city`, `deadline` in ISO format, `application_url`), and `evidence` with exact short excerpts from the exported `source_text` for each proposed field. Review results in admin. Never paste source content as instructions to an AI agent. See [AI prompt](docs/ai-enrichment.md).

## Hetzner deployment

Set an existing HTTPS subdomain and inspect the server's reverse proxy. Copy `.env.example` to `.env` on the server, fill the secret and database password, then run:

```sh
docker compose up -d --build
docker compose exec web python manage.py import_registry
docker compose exec web python manage.py verify_sources
docker compose exec web python manage.py createsuperuser
```

The web container runs migrations on start; static files are collected when the image is built. The scraper runs daily at 06:00 Sarajevo time, and at start for any enabled source not scraped in the last 20 hours (so a restart finishes an interrupted run). Before each scrape, it discards obsolete or unusable database connections; PostgreSQL also has connection health checks enabled. A failed scheduled run is logged and the loop continues to the next scheduled run. This does not add an immediate retry. The healthcheck sends the first `DJANGO_ALLOWED_HOSTS` entry as its `Host` header. Container logs rotate at 5 × 10 MB per service.

Production request errors, scheduler exceptions, and unexpected source errors include tracebacks in console logs even with `DJANGO_DEBUG=0`. The console handler writes to stderr, which Compose collects alongside stdout. Defaults are `WARNING` for Django and `INFO` for the board; optional `DJANGO_LOG_LEVEL` sets both (for example, `INFO` while investigating). Inspect `docker compose logs --tail=200 web scraper`; expected fetch/parser failures are recorded in each source's admin run history. One unexpected source failure still allows the other sources and the expiry pass to run.

Proxy the hostname to `127.0.0.1:8000`, forwarding `Host` and `X-Forwarded-Proto`. Use the actual HTTPS hostname in `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`. Set `PUBLIC_BASE_URL` to the same `https://` origin so canonical, Open Graph, sitemap and robots URLs do not depend on proxy headers. Once HTTPS works end to end, set `DJANGO_SECURE_SSL_REDIRECT=1` (`/health/` stays reachable over plain HTTP for the container healthcheck) and, after the hostname is final, `DJANGO_HSTS_SECONDS` (start small, e.g. `3600`; HSTS cannot be withdrawn from browsers that cached it). The database has no public port. For backups, run `docker compose exec -T db pg_dump -Fc -U diplomacyjobs diplomacyjobs > backups/diplomacyjobs-$(date +%F).dump` daily from host cron and delete dumps older than 30 days (`find backups -name '*.dump' -mtime +30 -delete`). Verify a restore before launch with `createdb` on a scratch database and `pg_restore --no-owner -d <scratch> <dump>`. Monitor `/health/` (liveness; the scheduler container waits on it), `/health/scrape/` (503 and the affected source URLs when an enabled source has not succeeded for 48 hours), Compose logs, and the source coverage page, which shows such sources as unavailable.

This checkout does not contain the server hostname, access credentials, or a complete verified mission inventory. The app should not be publicly described as comprehensive until the inventory and 10-source gate are complete.
