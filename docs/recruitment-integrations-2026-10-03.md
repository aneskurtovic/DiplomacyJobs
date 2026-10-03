# Seven recruitment audit integrations

Verified on **2026-10-03**, Europe/Sarajevo. These are local implementation and official-source scan results; deployment-network access and Linux CI for this change have not been checked.

All seven previously disabled audit leads now have adapters and passed their first local scrape. Five have complete listing coverage; two are deliberately partial. No current job was imported. All column values in the 15 existing job rows are identical in a database comparison with the pre-integration backup.

| Source | Adapter and checks | Current result |
| --- | --- | --- |
| UAE MoFA | Existing SuccessFactors parser; official Careers page links to `careers.mofa.gov.ae/search/`. Check total and unique rows, paginate by `startrow`, filter duty station. Missing result counts/changed shells fail. | Complete; two jobs, Dubai and Abu Dhabi, neither in BiH. |
| Türkiye Mostar | Public Turkish language switch in the same verified HTTPS session. Inspect only the local `#announcements` section; check publisher, publication year and recruitment terms. Ignore language exams and ministry announcements. | Complete; no 2026 recruitment notice. |
| Türkiye Sarajevo | Same adapter, scoped to the embassy publisher. The English translation omits its 2023 secretary notice, so Turkish is required. Current-year detail pages must independently identify the recruiting mission. | Complete; no 2026 recruitment notice. |
| Brazil | Selection folder → BHS notice page → original advert PDF. Ignore unrelated folder items and result attachments. Explicit `ENCERRADO / ZATVORENO` closes a process. | **Partial**; current selection is closed. Its scanned PDF has no extractable text. A future open scanned PDF fails explicitly and requires OCR/manual validation; no fabricated dates or location. |
| Spain | Spanish employment page, dated updates and recruitment categories. Read the latest call/revision PDF, associate final results with the matching older category, and distinguish a later new call. The revised inline deadline inherits its dated update's year. | Complete; Auxiliar process closed; revised deadline 13 July 2026, final results 13 August. No public job. |
| Slovenia | MZEZ active filter (`status=ongoing`, organization 3745); preserve both filters on next-page links. Keep only local embassy employment with independent detail duty-station evidence. Exclude observer secondments and jobs at other embassies. Repeated pages/empty shells fail. | Complete; no qualifying embassy employment in BiH. |
| Canada | Resolve the current public Gatsby manifest and data bundle hashes on every scan. Decode JSON string literals without executing JavaScript. Read the complete job and mission arrays; separately check employer, station, dates and application host. | **Partial**; 28 job records, none confirmed for the Sarajevo honorary consulate. Its mission is absent from the portal's 195-entry mission registry. The Budapest embassy serves BiH but jobs based there cannot be attributed to Sarajevo. Separate honorary-consulate notices remain outside this portal. |

All TLS checks remain enabled. Türkiye, Brazil and Spain opt into the existing Chrome TLS client. No authentication or JavaScript challenge solving was added.

## Local state and verification

- Seven source IDs: **37, 38, 40, 43, 44, 45, 47**. All first `ScrapeRun` records succeeded with zero importable candidates. [Machine-readable scan report](../data/recruitment_integration_2026-10-03.json).
- **39 enabled sources**, of which **35 complete and four partial** (the existing Sweden/RYCO plus Brazil/Canada).
- Coverage: **79 rows; 0 awaiting integration; 0 unchecked; 23 no-list; 17 unavailable; 7 with public jobs; 28 confirmed empty; 4 partial**. A partial feed retains unknown overall vacancy coverage.
- **15 stored job rows preserved exactly**; no new public or review job and no closure of an existing job. Backup: ignored `backups/before-seven-integrations-2026-10-03.sqlite3`.
- Partial card/API feeds preserve unseen published jobs without replacing their structured evidence with an unverified detail fetch.
- Migration **0025** registers the five new adapter choices. UAE reuses `rmk`; both Turkish sources share `turkey`.
- Django checks and migration drift checks passed. **154 SQLite tests: 153 passed, one PostgreSQL-only skip**; 19 new adapter regression tests. The PostgreSQL/Linux gate was not run for this change.
- Restarted the identified local launcher/child after verification. `/`, `/sources/?status=integration`, `/sources/?status=partial` and `/health/` returned HTTP 200. Local coverage: <http://127.0.0.1:8000/sources/>.

## Reproduction

Use the locked environment and `DJANGO_DEBUG=1` for local development. `manage.py migrate` and `manage.py import_registry` apply the parser settings. As before, registry import preserves existing sources' enablement and success timestamps.

`scripts/validate_recruitment_integrations.py [--adapter spain]` performs read-only live candidate checks. `scripts/activate_recruitment_integrations.py` applies the seven reviewed integrations and runs them against the local database; take a database backup first. A failed source is left disabled. This script does not run unrelated sources or global expiry. Successful activation stores its report and updates registry metadata. A fresh database must still execute a successful scrape before showing a source as monitored.

Raw public responses are ignored under `data/raw/integration_2026-10-03/`. The earlier [46-entry discovery audit](source-audit-2026-10-03.md) remains historical evidence. The 15 unresolved access/rendering cases, periodic discovery renewal and deployment work remain outstanding.
