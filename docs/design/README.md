# Design system proposal (2026-10-03)

Open [design-system.html](design-system.html) in a browser. It holds the audit, principles, foundations, component specs, redesigned screens and a phased rollout. It builds on the visual direction in [DesignProposal.html](../../DesignProposal.html) and does not replace it.

- [tokens.css](../../board/static/board/tokens.css): design tokens (global → alias → component, light and dark). The site links it before `site.css`, which uses only alias tokens. Dark mode is opt-in through `<html data-theme="auto">` and stays off until it has had a QA pass.
- [before/](before/): screenshots of the current site, from a local run with the real registry and 8 sample jobs.

Phase 1 of the rollout (the launch blockers) was done on 2026-10-03:

1. At 390px the header (`.site-nav` and the language switch) was 425px wide, so every page scrolled sideways on phones. Under 760px the header now has two rows, and the English job-card actions wrap at 320px.
2. Input borders (`#9aa5b1`) had 2.5:1 contrast, below the 3:1 WCAG 1.4.11 minimum. They now use `--color-border-control` (3.66:1).
3. site.css had no `:focus-visible` styles. It now has a 2px brand-blue focus outline.
4. On `/sources/`, "review" and "unavailable" shared the same amber pill. Review is now violet.
5. The 📍, ↗ and ◎ glyphs are now SVG icons (`templates/board/_icons.html`).

Phases 2–3 (filter bar, job card v2, mobile apply bar, sources grouping, dark theme) await owner review.
