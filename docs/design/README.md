# Design system proposal (2026-10-03)

Open [design-system.html](design-system.html) in a browser. It holds the audit, principles, foundations, component specs, redesigned screens and a phased rollout. It builds on the visual direction in [DesignProposal.html](../../DesignProposal.html) and does not replace it.

- [tokens.css](../../board/static/board/tokens.css): design tokens (global → alias → component, light and dark). The site links it before `site.css`, which uses only alias tokens. Dark mode is opt-in through `<html data-theme="auto">` and stays off until it has had a QA pass.
- [canvas/](canvas/): source files of the [Design canvas](https://claude.ai/artifact/2sbsjQcyQhKx6VimewJzoN) (overview, audit, foundations, components, rollout and five screens). The canvas is private until shared from its Share menu.
- [before/](before/): screenshots of the current site, from a local run with the real registry and 8 sample jobs.

Phase 1 of the rollout (the launch blockers) was done on 2026-10-03:

1. At 390px the header (`.site-nav` and the language switch) was 425px wide, so every page scrolled sideways on phones. Under 760px the header now has two rows, and the English job-card actions wrap at 320px.
2. Input borders (`#9aa5b1`) had 2.5:1 contrast, below the 3:1 WCAG 1.4.11 minimum. They now use `--color-border-control` (3.66:1).
3. site.css had no `:focus-visible` styles. It now has a 2px brand-blue focus outline.
4. On `/sources/`, "review" and "unavailable" shared the same amber pill. Review is now violet.
5. The 📍, ↗ and ◎ glyphs are now SVG icons (`templates/board/_icons.html`).

Phase 2 was done on 2026-10-03: the search bar with a Filters disclosure and removable chips, a trust strip, job card v2 with the shared deadline component, the job page summary grid and mobile apply bar, and self-hosted fonts.

Phase 3 was done on 2026-10-03, except the usability check, which needs real participants ([script](usability-check.md)):

1. `/sources/` is grouped by state, with sources that have jobs first. The four stat cards are the status filters, a stacked bar sums up coverage, groups longer than five rows link to their full list, and a name search ignores case and diacritics.
2. Dark mode is on: `base.html` sets `data-theme="auto"`, so the site follows the OS. Every text element on the job list, a job page, `/sources/` and `/report/` was checked in Chromium at WCAG AA in both themes; none failed.
3. Under `forced-colors: active`, pills, deadline chips, tags, chips and monograms get a border, and the coverage bar uses system colours. This was reviewed in code, not in Windows High Contrast mode.
4. Job cards show an employer monogram (`Organization.short_name`, set in the registry; otherwise an acronym or initials from the name). Hidden under 760px.
5. Each published, current job has an Open Graph image at `/jobs/<id>/share.png` (1200×630, title, employer, deadline and place), drawn with Pillow and cached for a day.
