# DiplomacyJobs continuation handoff

Updated: 2026-10-03 (Europe/Sarajevo). This records local and Linux CI verification; deployment readiness is still unverified.

## Latest completed work: seven audit integrations

See [implementation, limits and verification](docs/recruitment-integrations-2026-10-03.md) and [actual source runs](data/recruitment_integration_2026-10-03.json). All seven leads now have enabled adapters and successful first local scrapes: five complete (UAE, Türkiye Mostar/Sarajevo, Spain, Slovenia), two partial (Brazil scanned-PDF support and Canada honorary-consulate coverage). No current job was imported; all 15 existing job rows were compared with the backup and preserved exactly.

Verified local snapshot on 2026-10-03: 79 coverage rows, **0 awaiting integration**, 35 complete, 4 partial, 23 no-list, 17 unavailable, 0 unchecked; **39 enabled sources**. Django checks/migration drift passed; SQLite suite: **154 tests, 153 passed, one PostgreSQL-only skip**. Migration 0025 applied; updated server and source filters returned HTTP 200 at http://127.0.0.1:8000/sources/. Integration commit `7898c82` is pushed to `main`; [CI run 37080609044](https://github.com/aneskurtovic/DiplomacyJobs/actions/runs/37080609044) passed on Linux/Python 3.12 with 154 PostgreSQL tests and 153 SQLite tests plus one skip. Deployment was not performed. The seven audit leads no longer require initial parser integration; Brazil OCR and Canada honorary-consulate discovery still need follow-up.

The local database backup is `backups/before-seven-integrations-2026-10-03.sqlite3` (ignored). Parser settings and reviewed enablement are in `data/source_registry.json`. Use `scripts/validate_recruitment_integrations.py` for read-only live candidate checks; `--adapter spain` checks one adapter. `import_registry` preserves existing enablement. The backed-up local database has already been migrated, imported and activated through `scripts/activate_recruitment_integrations.py`; a future activation must again leave failed sources disabled. That script scans only these seven sources and does not run global expiry.

### Integration commit review

The prior GitHub run 37078478439 failed on both database jobs at migration drift: the tracked adapter choices required migration 0025, which was still untracked. This exact failure was reproduced against an isolated archive of HEAD; including 0025 clears the local migration check. Review also fixed partial card/API feeds so a published job outside current evidence remains unchanged instead of failing through a missing evidence lookup. The read-only validator now creates its report directory on fresh checkouts and returns a failing exit code for failed or unmatched checks. The final local suite passed 154 tests (153 passed, one PostgreSQL-only skip); The implementation is pushed as **`7898c821e51fe7d09d61f38064c222c00aabe56d`**. Both Linux jobs passed in [CI run 37080609044](https://github.com/aneskurtovic/DiplomacyJobs/actions/runs/37080609044): PostgreSQL 16 ran all 154 tests with no skips, SQLite ran 153 with one PostgreSQL-only skip; checks and migration drift also passed.

## Earlier completed work: discovery audit of all 46 unchecked entries

The counts and disabled-source state below describe the initial audit, before the seven integrations above. They are retained as historical evidence.

See [findings for every entry](docs/source-audit-2026-10-03.md), [findings and HTTP checks in JSON](data/recruitment_audit_2026-10-03.json), and [registry](data/source_registry.json).

- **23 no local recruitment list found**, **7 recruitment leads awaiting integration**, **15 unresolved access/rendering cases**, **1 obsolete OSCE duplicate**. Every original row is accounted for. A failed/incomplete check remains unavailable with unknown vacancy counts.
- Seven disabled leads: UAE MoFA Careers, Türkiye Mostar announcements, Brazil's 2026 selection folder, Spain's Spanish employment page, Slovenia's central MZEZ list, Türkiye Sarajevo announcements and Canada's Locally Engaged Staff portal. Malaysia, Greece, Pakistan and Ukraine also have disabled recruitment endpoints, but access remains unresolved. No new source was enabled.
- Corrected stale/wrong websites including Malaysia's kin.gov.my typo, Qatar's Italy address, Hungary/Poland/Netherlands old URLs and France's migration to ba.diplomatie.gouv.fr.
- Spain's Spanish page has a completed 2026 Auxiliar process (deadline 13 July, final results 13 August); its Bosnian page still holds 2025. Brazil's live page says closed while the search index says open. Neither was published as a current job.
- Migration **0023** adds Organization recruitment status, date, evidence URL and notes. `verified_at` remains diplomatic-presence verification; `Source.last_success_at` remains a successful scrape timestamp. `/sources/` shows evidence disclosures and the new integration/no-list states. Discovery findings expire after 90 days; missing/future evidence remains unchecked.
- Explicit `adapter_config.superseded_by` hides a disabled historical endpoint only while an enabled adapter for the same organization has that exact replacement URL. The OSCE root/history remain stored. Its active BiH adapter was rechecked read-only (`verify_sources --source 10`): **one 2026 lead**, no failure.
- `import_registry` applies complete recruitment metadata atomically and repeatably while preserving existing source status/enablement, timestamps and jobs. Presence-only homepages/directories were not created as vacancy sources.
- Local database backed up before migration/import at ignored `backups/before-recruitment-audit-2026-10-03.sqlite3`. Migration and import applied. Coverage: **79 rows, 0 unchecked, 23 no-list, 7 integration, 17 unavailable (15 audit + UK/UNICEF), 30 complete and 2 partial**. Still **32 enabled sources, 15 stored jobs, 13 publicly visible jobs**. No audit job publication/closure/deletion.
- Certificate verification stayed enabled; no JavaScript challenge was solved. Raw responses are ignored under `data/raw/source_audit_2026-10-03/`; committed evidence includes requested/final URLs, HTTP status/error, size, title and timestamps. Search-index evidence is labelled and is weaker than live page verification.
- Audit commit **`e19a79a1aa0d592d2e830b471dc4b56606e9ed63`** is pushed to `main`. Local suite: **132 discovered, 131 passed, one PostgreSQL-only skip**. Both Linux/Python 3.12 jobs succeeded in [run 37073582887](https://github.com/aneskurtovic/DiplomacyJobs/actions/runs/37073582887): PostgreSQL 16 passed **132 tests, no skips**; SQLite passed **131 with one skip**. System and migration drift checks passed on both. Seven new tests cover imports, unknown counts, evidence expiry, source failure precedence and safe replacement.
- Restarted the local server and stopped the identified obsolete repository launcher/child. The updated `/sources/` returns HTTP 200 with 79 rows, 0 unchecked, 23 no-list, 7 integration and 17 unavailable; each status filter was checked over HTTP. At the initial audit, the server launcher was PID 1092 and its child PID 36476; both were subsequently stopped during the integration restart. Future restarts must stop both the validated launcher and child; Windows Python venv launchers can leave the serving child alive. URL: **http://127.0.0.1:8000/sources/**.
- After restart, jobs/feed/admin login/health/static CSS returned HTTP 200. All 23 no-list rows include an evidence disclosure and display an unknown vacancy count.

### Reliability push and Linux CI completed

- Reliability commit **`fea33108b6a5fca3226620a07dabf6a11ca137a8`** is pushed to `main`.
- Both Linux/Python 3.12 jobs passed in [run 37071234992](https://github.com/aneskurtovic/DiplomacyJobs/actions/runs/37071234992): PostgreSQL 16 passed all 125 tests (no skips), SQLite passed 124 with one PostgreSQL-only skip; checks and migration drift passed.
- Authentication works outside the network sandbox. The gh token lacks workflow scope, so the workflow push used existing Git Credential Manager with per-command helper overrides. Persistent auth/config was not changed. Earlier sandbox authentication failures were environmental.

### Current next steps

1. Add verified OCR/manual handling for Brazil's open scanned vacancy PDFs and investigate a separate recruitment source for Canada's Sarajevo honorary consulate. Both enabled adapters remain explicitly partial until those gaps are resolved.
2. Keep the now-passing Linux/Python 3.12 SQLite/PostgreSQL CI gate green for subsequent changes. Validate current source access from the actual deployment network before launch.
3. Resolve the 15 access/rendering cases from the deployment network; revisit no-list discoveries within 90 days. Full international/honorary reconciliation beyond these 46 remains outstanding.
4. Recheck prior admin credential rotation and the manually published RYCO Tirana role, then verify Hetzner deployment, HTTPS, backup restore and daily scraping. These remain unverified; push/CI are not deployment proof.

The sections below retain the recovery history. The local integration state and current next steps above supersede earlier pending integration work. Historical push/CI results apply only to their recorded commits. Verify the current local server's process identity before restarting it; historical PIDs must not be reused blindly.

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

## Earlier next steps (superseded by current steps above)

1. Restore authenticated GitHub access when available, include the workflow in the next commit, and run both Linux database jobs. Record their commit/run IDs and results here. Fix any PostgreSQL failures before declaring the reliability gate complete. Alternatively, run the documented checks against a dedicated development PostgreSQL 16 database with test-database creation privileges and permission to terminate its own connections. Do not use production credentials.
2. Recheck prior-session content/security review items: local admin credential rotation and the manually published RYCO Tirana role. Their status was not verified during this continuation; use admin review rather than assuming the listing's publication was intended. No credential values belong in this file.
3. Reconcile the remaining international and honorary-consulate inventory and validate missing official recruitment endpoints. Retain honest blocked/unsupported statuses; avoid disabling certificate verification or solving JavaScript challenges. The detailed checked leads are in BACKLOG.
4. Verify the actual Hetzner host, hostname, proxy/HTTPS, migrations, static assets, backup restore, source access, and daily scheduling. Check `/health/`, `/health/scrape/`, logs, public listings, and the source coverage page. Deployment access and hostname are not present in the checkout.
5. Done 2026-10-03 (commits 31de56c, 3074958 and the `PUBLIC_BASE_URL` commit): pagination links and 404s, snapshot index (migration 0024), `PUBLIC_BASE_URL`, admin run/snapshot filters without loading texts. Still open: decide the retention policy before adding destructive trimming. Source expansion, email alerts, structured job data, and widening employer scope require separate product decisions.

The historical Linux/PostgreSQL reliability gate passed. The seven recruitment adapters now pass local scans; Brazil/Canada coverage gaps, unresolved source access, inventory reconciliation and deployment validation remain the next work. Integration Linux/PostgreSQL CI has passed.
