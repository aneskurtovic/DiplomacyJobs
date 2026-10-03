# Design system proposal (2026-10-03)

Open [design-system.html](design-system.html) in a browser. It holds the audit, principles, foundations, component specs, redesigned screens and a phased rollout. It builds on the visual direction in [DesignProposal.html](../../DesignProposal.html) and does not replace it.

- [tokens.css](tokens.css): drop-in design tokens (global → alias → component, light and dark). Link it before `board/static/board/site.css`, then replace raw hex values with the alias tokens.
- [before/](before/): screenshots of the current site, from a local run with the real registry and 8 sample jobs.

Launch blockers from the audit (Phase 1 in the rollout):

1. At 390px the header (`.site-nav` and the language switch) is 425px wide, so every page scrolls sideways on phones.
2. Input borders (`#9aa5b1`) have 2.5:1 contrast, below the 3:1 WCAG 1.4.11 minimum.
3. site.css has no `:focus-visible` styles.
4. On `/sources/`, "review" and "unavailable" share the same amber pill, and "pending" and "not found" share the same grey pill.
