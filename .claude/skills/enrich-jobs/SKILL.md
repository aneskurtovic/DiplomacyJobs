---
name: enrich-jobs
description: Fill missing requirement fields (education level, years of experience, fields of study) of DiplomacyJobs adverts with quote-backed proposals from Haiku subagents, then import them. Use when the user asks to enrich jobs, fill missing requirements, or improve the education/experience/field filters.
---

# Enrich job requirements

Runs only when the owner asks. The rules in `board/requirements.py` fill these fields on every scan; this fills the gaps they miss (foreign-language adverts, unusual wording). The proposals come from `enricher` subagents on Haiku (`.claude/agents/enricher.md`); this session exports, splits, imports and checks. Imported values are marked as AI fields: the rules leave them alone, and when the advert's text changes they are dropped and the rules read the new text.

## Steps

Work from the repository root with `DJANGO_DEBUG=1`; batch files go in the scratchpad. Back up the local database first (`backups/db-before-enrichment-<timestamp>.sqlite3`). On the server, run the commands with `docker compose exec web python manage.py …` and copy the files across.

1. Export published jobs with a missing field:

   ```
   DJANGO_DEBUG=1 .venv311/Scripts/python.exe manage.py export_enrichment --status published --missing-requirements --limit 40 > <scratchpad>/enrich-batch.jsonl
   ```

   An empty file means nothing is missing. Stop and say so.

2. Split the batch into chunks of up to 8 lines and start one `enricher` agent per chunk, all in one message so they run in parallel, each with absolute input and output paths (`enrich-out-N.jsonl`).

3. Spot-check before importing: for a few proposals, read the quote in the source text and confirm it states that value as a requirement (not an asset, not a sub-requirement). Delete lines you disagree with.

4. Import each output file:

   ```
   DJANGO_DEBUG=1 .venv311/Scripts/python.exe manage.py import_enrichment <scratchpad>/enrich-out-N.jsonl
   ```

   The importer checks that each quote is in the advert and backs the value (a level the rules recognise, the number of years), and rejects any proposal that conflicts with a stored value. Rejections are expected; do not force them.

5. Report how many jobs were exported, proposed, imported and rejected (with the common reasons).
