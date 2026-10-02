# DiplomacyJobs continuation handoff

Updated: 2026-10-03 (Europe/Sarajevo). This records local verification, not deployment readiness.

## Goal and boundaries

Build a Bosnian-language board of trustworthy, current, paid individual opportunities at diplomatic missions and international governmental organizations with duty stations in BiH. Public listings link to official employers; uncertain facts stay in admin review. Collection is limited to 2026. GIZ and other national agencies remain outside the agreed scope. Preserve the approved design and distinguish unavailable sources from successful empty listings.

## Recovered state

- Branch: `main`; starting HEAD: `e5a26261de07ee0429b1edc25eecf98579664a1b` (Lanteria/RAI listing guards). Local tracking refs showed no unpushed reachable commits; remote state was not refreshed. No stashes were present.
- Claude stopped while adding database cleanup to `run_scraper_schedule`, PostgreSQL health checks and console logging to settings. The untracked GitHub workflow already included a SQLite/PostgreSQL matrix. These changes were preserved and completed.
- Git inspection found unreachable commit `eb52b7881bfd9c51bb4f5cc8928c20dfea611b04`, containing an older SQLite-only workflow. Do not restore it over the newer matrix workflow.
- The registry snapshot contains 79 organizations and 32 enabled sources: 30 complete and two partial (Sweden, RYCO). Prior live checks were recorded on 2026-10-02; this continuation did not re-fetch employer sites.
- A read-only local database check found 14 stored published jobs, one closed job, and 32 enabled sources. Stored publication counts are not a guarantee that every row is currently visible or meets the launch review criteria. No local job/source data was edited during this continuation.

## Reliability work completed locally

- Scheduler connection cleanup now runs inside the exception handler before every scrape. Cleanup or scrape failures include a traceback and leave the loop able to run again. The existing 06:00 Sarajevo schedule, startup recovery, and 20-hour recent-run behavior are preserved; failures do not introduce an immediate retry.
- PostgreSQL has `CONN_HEALTH_CHECKS=True`; obsolete/unusable connections are discarded before each scheduled scrape.
- Console output has timestamps, severity, and logger names. Production request errors reach stderr with DEBUG off. Unexpected per-source exceptions retain tracebacks while subsequent sources and expiry still run; expected fetch/parser errors remain recorded in admin run history.
- `DJANGO_LOG_LEVEL` is documented in `.env.example` and README. Defaults remain Django `WARNING` and board `INFO`; the variable sets both. Compose captures stderr and stdout.
- Regression coverage now exercises the actual console handler, repeated scheduler runs and failures, redirect/domain boundaries, old archive exclusion, oversized listing protection, and selected undated-job renewal. Existing interrupted-startup, oversized-URL, and stale-source tests were reused. Scheduler startup tests isolate connection cleanup from TestCase's database transaction.
- A PostgreSQL-only TransactionTestCase terminates its own Django connection in the runner's disposable test database, confirms the connection is unusable, then checks that two scheduler runs query successfully. It never targets a production connection. PostgreSQL 16's termination timeout makes the test wait for the connection to end.
- GitHub Actions defines independent Linux/Python 3.12 jobs for SQLite and PostgreSQL 16, with locked dependencies, Django checks, migration drift checks, and the full suite. One failing matrix job does not cancel the other. Workflow token permissions are limited to reading repository contents.
- README, PLAN and BACKLOG now link the continuation state and distinguish implemented checks from pending execution. No schema migration or public API change was needed.

## Verification evidence

Existing `.venv311` uses Python 3.11.3; installed dependency versions match `requirements.lock`. Run from the repository root:

```powershell
$env:DJANGO_DEBUG = '1'
.venv311\Scripts\python.exe manage.py check
.venv311\Scripts\python.exe manage.py makemigrations --check --dry-run
.venv311\Scripts\python.exe manage.py test board --noinput
```

Results on 2026-10-02:

- Django system check: no issues.
- Migration drift: no changes detected.
- Full SQLite suite: 125 discovered, 124 passed, one skipped (PostgreSQL recovery).
- Focused reliability/ingestion/admin suite: 40 discovered, 39 passed, one skipped.
- Expected invalid-Host and stale-source tests emit error logs. A missing local `staticfiles` directory produces a warning; image build collects static files. These messages did not fail the suite.
- `.venv` uses Python 3.14.7. Its earlier run encountered four temporary-directory permission errors in registry/enrichment tests; the verified local path is `.venv311`. Production and CI target Python 3.12, which is not installed here.
- No Docker executable, PostgreSQL executable/service, or local PostgreSQL installation was found. The recovery integration test and Linux matrix have not been executed here.
- `gh auth status` reported failed authentication for the active account. No workflow push or authenticated CI verification was performed. Treat the earlier session's workflow-scope issue as historical until authentication is restored and checked.

### Main push and local development follow-up (2026-10-03)

- The user requested committing/pushing the continuation to `main` and starting local development. Include the CI workflow and this handoff in the continuation commit.
- The full SQLite suite passed again: 124 passed, one PostgreSQL-only test skipped. Django checks passed; all existing local database migrations are applied.
- A fresh `git fetch origin` succeeded outside the network sandbox; local HEAD and `origin/main` matched before the continuation commit. GitHub authentication also succeeds outside the sandbox. Earlier sandbox authentication failures did not establish that the stored credential was invalid.
- The active GitHub CLI token has repository access but lacks the `workflow` scope. A push containing the new workflow may require a credential with that permission. Remote CI execution remains pending until the workflow is published.
- Local development runs on `http://127.0.0.1:8000/` using `.venv311`, `DJANGO_DEBUG=1`, and the existing SQLite database. Jobs, `/sources/`, `/feed/`, `/admin/login/`, `/health/`, and `/static/board/site.css` returned HTTP 200. Logs are ignored under `data/raw/devserver.out.log` and `data/raw/devserver.err.log`.
- The server was started as a hidden background process with `--noreload`. Restart it after Python changes; use `.venv311\Scripts\python.exe manage.py runserver 127.0.0.1:8000` with `DJANGO_DEBUG=1` for interactive development with automatic reload.

## Ordered next steps

1. Restore authenticated GitHub access when available, include the workflow in the next commit, and run both Linux database jobs. Record their commit/run IDs and results here. Fix any PostgreSQL failures before declaring the reliability gate complete. Alternatively, run the documented checks against a dedicated development PostgreSQL 16 database with test-database creation privileges and permission to terminate its own connections. Do not use production credentials.
2. Recheck prior-session content/security review items: local admin credential rotation and the manually published RYCO Tirana role. Their status was not verified during this continuation; use admin review rather than assuming the listing's publication was intended. No credential values belong in this file.
3. Reconcile the remaining international and honorary-consulate inventory and validate missing official recruitment endpoints. Retain honest blocked/unsupported statuses; avoid disabling certificate verification or solving JavaScript challenges. The detailed checked leads are in BACKLOG.
4. Verify the actual Hetzner host, hostname, proxy/HTTPS, migrations, static assets, backup restore, source access, and daily scheduling. Check `/health/`, `/health/scrape/`, logs, public listings, and the source coverage page. Deployment access and hostname are not present in the checkout.
5. Evaluate deferred improvements from Claude's final review: pagination links and canonical behavior; snapshot lookup performance; unused `PUBLIC_BASE_URL`; admin run/snapshot filters and avoiding loading full text in changelists. Decide the retention policy before adding destructive trimming. Source expansion, email alerts, structured job data, and widening employer scope require separate product decisions.

The next executable task is the Linux/PostgreSQL verification gate when a test database or CI access is available. Inventory and deployment preparation can continue while access is unavailable; neither historical source checks nor a green SQLite suite prove production readiness.
