# DiplomacyJobs continuation handoff

Updated: 2026-10-03 (Europe/Sarajevo). This is the only file that records current counts and verification results; [PLAN.md](PLAN.md) holds scope and launch gates, [BACKLOG.md](BACKLOG.md) the work list. Nothing has been deployed.

## Current state (verified 2026-10-03, local SQLite)

- **Commits:** `8ec1cc8` is the last pushed commit; [CI run 37111397154](https://github.com/aneskurtovic/DiplomacyJobs/actions/runs/37111397154) passed on it (Linux/Python 3.12, SQLite and PostgreSQL 16). Later local commits, including the new adapters and migration 0028 (`be69b0a`), are **not pushed and have no CI run yet**.
- **Tests:** 170 discovered locally: 169 passed, one PostgreSQL-only skip. Django checks and migration drift are clean.
- **Registry:** 86 organizations (41 embassies, 7 consulates, 6 honorary consulates, 28 international organizations, 2 INGOs, 2 aggregators); 53 sources, **46 enabled**.
- **Coverage on `/sources/`** (86 rows): **42 complete** (38 official mission/IGO sources plus 2 aggregators and 2 INGOs; 9 with published jobs, 33 empty), **4 partial** (Sweden, RYCO, Brazil, Canada), **17 unavailable** (15 unresolved audit cases plus UK and UNICEF), **23 no local recruitment list**, 0 awaiting integration, 0 unchecked.
- **Jobs:** 15 published (all visible on the board), 0 in review, 9 closed. Content review done 2026-10-03 (see below).

## Owner decisions (2026-10-03)

- A full reconciliation against the BiH Ministry of Foreign Affairs directory is **not** needed. The registry is the set of employers we choose to monitor.
- GIZ may come in through a third-party board (mreza-mira.net). More generally, aggregators and local boards are acceptable sources; the direct employer is preferred and syndicated jobs are attributed.
- INGOs and development agencies hiring in BiH are in scope (Save the Children and CRS are enabled).
- Next work, in this order: review published jobs (done 2026-10-03), then coverage (recheck the 2026-10-02 dead-end leads (done 2026-10-03), GIZ, UNDP consultant notices, the four partial sources, the 15 inaccessible sites).

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

## Next steps

1. **GIZ** via mreza-mira.net, filtered to GIZ.
2. **UNDP consultant notices** from UNDP's procurement-notices system, BiH only.
3. **Partial sources:** Sweden and RYCO full listings, Brazil scanned PDFs, Canada honorary-consulate notices.
4. **The 15 inaccessible sites** (listed in BACKLOG). Some may only be reachable from the server network.
5. **Deployment:** Hetzner, HTTPS, `verify_sources` from the server, daily scrape, backup restore. Push and CI are not deployment proof.

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
