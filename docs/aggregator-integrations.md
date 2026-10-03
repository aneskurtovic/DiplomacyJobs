# International job aggregators

ReliefWeb (BiH country filter C40) and Impactpool (work-location filter 28) extend
the official-source inventory. Their adapters are being implemented; this first
milestone adds cross-source identity and employer display.

The board and Atom feed choose one record per vacancy, preferring the direct
employer. Source records, snapshots, manual edits and scan lifecycles remain
independent. A syndicated record cannot reopen an official record held for review,
withdrawn, disabled or closed. This decision is recomputed when reading the board,
so scrape order and admin changes cannot leave a stale duplicate flag.

Matching uses the original vacancy/application URL (tracking removed, requisition
parameters retained), with a specific UNICEF requisition URL normalization. The
fallback requires an exact normalized title, an explicitly matched employer,
the same nonempty city and the same deadline. Similar titles are insufficient.
Publication dates more than 45 days apart represent separate recruitment rounds.
Shared careers homepages do not identify a vacancy. Unknown employer aliases and
uncertain matches stay separate. Aggregator employer names are retained in field
evidence, used by the board, filters and Atom, and shown with portal attribution.

Local first-milestone verification: 161 tests, 160 passed and one PostgreSQL-only
skip. Linux CI and live integration results will be recorded after implementation.
