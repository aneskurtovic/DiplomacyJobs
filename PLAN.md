# DiplomacyJobs MVP plan

This file holds the goal, scope and launch gates. [BACKLOG.md](BACKLOG.md) tracks the work; [HANDOFF.md](HANDOFF.md) holds the current verified numbers and next steps. Volatile counts live only in HANDOFF.

## Goal and scope

Build a Bosnian-language board of current, paid, individual jobs with a duty station in Bosnia and Herzegovina, at:

- diplomatic missions (embassies, consulates, honorary consulates);
- international governmental organizations;
- international NGOs and development agencies that hire in BiH (for example Save the Children, CRS, GIZ).

Every public listing links to where the employer advertised it and carries the evidence needed for review. Uncertain facts stay in admin review.

**Source preference.** Use the employer's own recruitment listing when one exists. Aggregators (ReliefWeb, Impactpool) and local third-party boards (for example mreza-mira.net for GIZ) are acceptable when they are the only place the job appears, or as a secondary source. The board shows one record per vacancy, prefers the direct employer, and attributes syndicated jobs to the portal.

**Collection window.** Ingest only **2026** jobs. A publication date or dated URL proves the year. A 2026 deadline without a publication date qualifies only for admin review. Undated listings with no 2026 evidence are excluded. Do not import older archives.

**Inventory.** The registry is the list of employers we choose to monitor, grown from known BiH employers, aggregator findings and source-discovery checks. A full reconciliation against the BiH Ministry of Foreign Affairs directory is **not** required (owner decision, 2026-10-03); `data/mfa_inventory.json` remains as reference data.

## Sources

1. For each employer, find the actual recruitment endpoint. Keep its homepage, vacancy list and application link separate. Record "no source found", "blocked" and "parser failure" honestly, with a date, evidence URL and note; renew discovery findings within 90 days.
2. Build a small adapter per live source. Handle pagination, or mark a limited feed as partial. A source counts as complete only when its active listings are covered and a live fetch succeeds.
3. Keep TLS verification on and never solve JavaScript challenges. Chrome TLS impersonation is allowed per source through `adapter_config.impersonate`.

## Collection and publication

1. Fetch daily with bounded requests. Skip clearly older dated archives before opening details; cap detail fetches per source and fail the run if the cap is exceeded. A failed or partial scan never closes jobs because they were unseen.
2. Preserve raw source text, canonical URL, dates, duty station and evidence. Deduplicate within a source by URL and across sources by vacancy. Publish only proven current, paid, BiH-based individual roles; everything uncertain goes to admin review.
3. Optional AI enrichment makes titles and descriptions readable in Bosnian, with quoted evidence and human review. Scraped facts and admin corrections stay authoritative.
4. Close expired jobs automatically. Log every source run and show coverage on `/sources/`, so an empty board is never confused with complete coverage.

## Public site

`DesignProposal.html` is the visual direction for `/sources/` and the job list, using real database counts. Search, filters, official application links and mobile layout are required.

## Launch gates

Launch only when all of these hold:

1. At least ten complete sources pass live checks **from the deployment network**.
2. SQLite and PostgreSQL CI jobs pass on the release commit.
3. The Hetzner deployment, HTTPS, scheduled scraping and a backup restore are verified on the real host.
4. Content review is done: every published job meets the publication rule above.
5. The coverage work in BACKLOG P0 is done or explicitly accepted as a known gap.

Production failures must reach console logs with DEBUG off. Each scheduled scrape refreshes database connections, and a failed run must not block the next one.
