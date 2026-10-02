# DiplomacyJobs

Bosnian-language job board for roles in diplomatic missions and international governmental organizations based in Bosnia and Herzegovina. Listings link to official employers. Source coverage is explicit; an unavailable source is never presented as having zero vacancies.

The current collection window is **2026 only**. The scraper skips clearly older dated archives before fetching job details, bounds each source to 100 possible 2026 details per run, and stores only qualifying 2026 candidates. Deadline-only leads require admin review. See [the MVP plan](PLAN.md) and [backlog](BACKLOG.md).

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

Browse `http://127.0.0.1:8000/`, coverage at `/sources/`, an Atom feed of new jobs at `/feed/` (accepts the board's `q`, `employer`, `city`, `type` and `scope` filters), and admin at `/admin/`. Development defaults to SQLite. The imported registry enables the twenty-two complete sources that passed live checks; the board may still be empty when none has an open 2026 vacancy.

## Operations

The [source registry](data/source_registry.json) is an evidence-backed starting set. The [MFA candidate inventory](data/mfa_inventory.json) distinguishes local and nonresident missions. Complete international and honorary-consulate reconciliation before launch. Twenty-two complete sources (Denmark, Italy, EU Delegation, UN in BiH, OHR, EUFOR, EBRD, RCC, US Embassy via ERA, Japan, Switzerland, UNDP, UNFPA, UN Women, IOM, UNHCR, Council of Europe, OSCE, Ireland, UN Secretariat, World Bank Group, IMF) have passed live checks. All other sources require validation before enabling. The launch threshold is at least 10 complete working sources. Sources that refuse non-browser TLS fingerprints (Japan, Switzerland, Ireland, OSCE search) set `"impersonate": true` in `adapter_config` to fetch with a Chrome TLS fingerprint; all others use the honest bot user agent. JavaScript challenges are not solved. `import_registry` updates notes and `adapter_config` of existing sources (matched by URL, even when moved to another organization), changes the adapter only while a source is disabled (an enabled source whose registry adapter differs keeps its adapter and settings, with a warning), and never changes status or enablement; do those in admin. An organization entry may carry `previous_name` to rename an existing organization.

Run one fetch with `python manage.py scrape_jobs --source ID` or all enabled sources with `python manage.py scrape_jobs`. `python manage.py verify_sources [--all]` fetches each listing and reports leads or errors without writing to the database; run it first from a new server network. The dedicated Compose scheduler runs this daily. Errors are recorded per run; a failed run does not remove jobs. Scrape details are visible in admin. The scraper lock file is `/tmp/diplomacyjobs-scrape.lock` in the container.

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

The web container runs migrations on start; static files are collected when the image is built. The scraper runs daily at 06:00 Sarajevo time, and at start for any enabled source not scraped in the last 20 hours (so a restart finishes an interrupted run). The healthcheck sends the first `DJANGO_ALLOWED_HOSTS` entry as its `Host` header. Container logs rotate at 5 × 10 MB per service.

Proxy the hostname to `127.0.0.1:8000`, forwarding `Host` and `X-Forwarded-Proto`. Use the actual HTTPS hostname in `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`. Once HTTPS works end to end, set `DJANGO_SECURE_SSL_REDIRECT=1` (`/health/` stays reachable over plain HTTP for the container healthcheck) and, after the hostname is final, `DJANGO_HSTS_SECONDS` (start small, e.g. `3600`; HSTS cannot be withdrawn from browsers that cached it). The database has no public port. For backups, run `docker compose exec -T db pg_dump -Fc -U diplomacyjobs diplomacyjobs > backups/diplomacyjobs-$(date +%F).dump` daily from host cron and delete dumps older than 30 days (`find backups -name '*.dump' -mtime +30 -delete`). Verify a restore before launch with `createdb` on a scratch database and `pg_restore --no-owner -d <scratch> <dump>`. Monitor `/health/` (liveness; the scheduler container waits on it), `/health/scrape/` (503 and the affected source URLs when an enabled source has not succeeded for 48 hours), Compose logs, and the source coverage page, which shows such sources as unavailable.

This checkout does not contain the server hostname, access credentials, or a complete verified mission inventory. The app should not be publicly described as comprehensive until the inventory and 10-source gate are complete.
