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

Browse `http://127.0.0.1:8000/`, coverage at `/sources/`, and admin at `/admin/`. Development defaults to SQLite. The imported registry enables the eighteen complete sources that passed live checks; the board may still be empty when none has an open 2026 vacancy.

## Operations

The [source registry](data/source_registry.json) is an evidence-backed starting set. The [MFA candidate inventory](data/mfa_inventory.json) distinguishes local and nonresident missions. Complete international and honorary-consulate reconciliation before launch. Eighteen complete sources (Denmark, Italy, EU Delegation, UN in BiH, OHR, EUFOR, EBRD, RCC, US Embassy via ERA, Japan, Switzerland, UNDP, UNFPA, UN Women, IOM, UNHCR, Council of Europe, OSCE) have passed live checks. All other sources require validation before enabling. The launch threshold is at least 10 complete working sources. Sources that refuse non-browser TLS fingerprints (Japan, Switzerland, OSCE search) set `"impersonate": true` in `adapter_config` to fetch with a Chrome TLS fingerprint; all others use the honest bot user agent. JavaScript challenges are not solved. `import_registry` does not change adapter, status or enablement of existing sources; change those in admin.

Run one fetch with `python manage.py scrape_jobs --source ID` or all enabled sources with `python manage.py scrape_jobs`. The dedicated Compose scheduler runs this daily. Errors are recorded per run; a failed run does not remove jobs. Scrape details are visible in admin. The scraper lock file is `/tmp/diplomacyjobs-scrape.lock` in the container.

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
docker compose exec web python manage.py migrate
docker compose exec web python manage.py import_registry
docker compose exec web python manage.py createsuperuser
```

Proxy the hostname to `127.0.0.1:8000`, forwarding `Host` and `X-Forwarded-Proto`. Use the actual HTTPS hostname in `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`. The database has no public port. Run `docker compose exec -T db pg_dump -U diplomacyjobs diplomacyjobs > backup.sql` from the host for a backup. Verify restoring that backup to a separate PostgreSQL database before launch. Monitor `/health/`, Compose logs, and the source coverage page.

This checkout does not contain the server hostname, access credentials, or a complete verified mission inventory. The app should not be publicly described as comprehensive until the inventory and 10-source gate are complete.
