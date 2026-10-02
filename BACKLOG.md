# DiplomacyJobs MVP backlog

Priority follows the product requirement: the board must show trustworthy, current jobs from official sources. `DesignProposal.html` defines the public visual direction and will be integrated after ingestion is credible.

## P0 — Source coverage and trustworthy ingestion

- [ ] Complete resident embassy, career consulate, honorary consulate, and international organization inventory against current BiH MFA records. Record official website, recruitment endpoint, evidence, and last verification date for each.
- [ ] Validate official recruitment endpoints from the server network. Keep homepage, recruitment portal, and application URL separate. Record no source found, blocked, and parser failure separately.
- [ ] Integrate and verify at least 10 operational sources before public launch. Prioritize source families that cover many organizations, then individual embassy sites. A working source with zero open jobs counts; an inaccessible source does not.
- [ ] Handle active-list pagination and changed page structure without falsely closing existing jobs.
- [ ] Publish only proven current, paid, BiH-based individual roles. Keep uncertain or archived entries in admin review. Prove deadline and location extraction on representative real vacancies.
- [ ] Run the daily fetch from Hetzner, verify successful empty listings versus failures, and inspect resulting public jobs.

## P1 — Operations and data quality

- [x] Django models, admin, public list, source coverage page, scheduler command, source run history, and optional AI batch interface are implemented.
- [x] Query parameters remain in job URLs; fetch failures and excessive link counts prevent absence-based closure.
- [ ] Validate a full deployment on the actual Hetzner host and HTTPS subdomain, including migrations, backup restore, static assets, source access, and scheduled runs.
- [ ] Confirm AI imports and manual corrections survive subsequent source updates; handle changed source text through review.
- [ ] Add source-specific handling for PDFs, dynamically rendered portals, and paid internships only where an official source requires it.

## P2 — Public design

- [ ] Apply `DesignProposal.html` typography, colors, header, coverage summary, legend, and source table to the real `/sources/` page. Replace all mock numbers and statuses with database values.
- [ ] Carry the same visual language into the jobs page; retain responsive search, filters, and official application links.

## Current constraints

The verified seed registry contains six organizations and no enabled sources yet. The full MFA inventory, ten-source launch gate, and Hetzner deployment are outstanding. Public counts must reflect this reality rather than the mock figures in the design proposal.
