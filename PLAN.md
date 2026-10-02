# DiplomacyJobs MVP plan

## Goal and boundary

Build a Bosnian-language board for current paid jobs at diplomatic missions and international governmental organizations with a duty station in Bosnia and Herzegovina. Every public listing links to an official source and carries the evidence needed for review. For the current collection phase, ingest only **2026** jobs. A source publication date or dated URL can prove the year. A 2026 deadline without a publication date qualifies only for admin review. Undated listings with no 2026 evidence are excluded. Do not import older archives.

## Discovery and source registry

1. Reconcile embassies, consulates, honorary consulates, and relevant international organizations against the BiH Ministry of Foreign Affairs directory and each organization's official site. Record the organization, local presence, evidence URL, site, and verification date.
2. Find the actual recruitment endpoint for each organization. Distinguish its homepage from a vacancy list and from the job application link. Mark blocked or absent endpoints honestly.
3. Build a small adapter per live source. Handle pagination or explicitly mark limited feeds as partial. A source counts toward the launch gate only when its active listings are covered and a live fetch succeeds.

## Collection and publication

1. Fetch official lists daily with bounded requests. Skip links in clearly dated older archives before opening detail pages; cap ambiguous leads per source and fail the run if the cap is exceeded. Refresh known jobs from partial feeds directly. An unsuccessful or partial scan must never close jobs because they were unseen.
2. Preserve the raw source text, canonical URL, dates, duty station, and evidence. Deduplicate by source and URL. Publish only current, paid, BiH-based individual opportunities with enough proof; send uncertainty to admin review.
3. Use optional AI enrichment to make titles and descriptions readable in Bosnian, with quoted source evidence and human review. Scraped source facts and admin corrections remain authoritative.
4. Close expired jobs automatically. Log every source run and show coverage status so an empty board is not confused with complete coverage.

## Public site and launch

Implement `DesignProposal.html` using real database counts and statuses. Carry its visual language into the job list, with search, filters, official application links, and mobile layout. Launch only after the inventory is reconciled, at least ten complete sources pass live checks from the deployment network, both SQLite and PostgreSQL CI jobs pass, a host deployment and backup restore are verified, and content review is complete. `BACKLOG.md` tracks the current work and evidence gaps; `HANDOFF.md` records the latest verified continuation state.

Production failures must be visible in console logs with DEBUG off. Each scheduled scrape must refresh database connections after the daily sleep, and a failed run must allow the next scheduled run to proceed. Verify connection recovery against a disposable PostgreSQL database as well as the SQLite regression suite.

Recruitment discovery is tracked separately from diplomatic presence and successful scraping. Every discovery finding requires a date, official evidence URL and explanation, and must be renewed within 90 days. “No source found” and “awaiting integration” retain unknown vacancy counts. The [46-entry audit](docs/source-audit-2026-10-03.md) records the completed discovery work and unresolved access/parser tasks; disabled obsolete endpoints may be replaced in coverage without deleting their history.
