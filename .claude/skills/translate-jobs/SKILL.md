---
name: translate-jobs
description: Write Bosnian and English versions of DiplomacyJobs adverts that need them (foreign-language adverts, and adverts with no Bosnian or English version), then import them into the database. Use when the user asks to translate job adverts, run translations, or fill missing BS/EN versions.
---

# Translate job adverts

Translation runs only when the owner asks for it, never after a scrape. The writing is done by `translator` subagents on Haiku (`.claude/agents/translator.md`, which holds the output format and writing rules); this session exports, splits, imports and checks. No API key or app-side model call is involved. The job page shows these versions as "automatski prijevod"; scraped facts (deadline, city, requirements) stay authoritative and are shown separately.

## Steps

Work from the repository root. Use the scratchpad directory for the batch files. Add `DJANGO_DEBUG=1` locally. On the server, run the same commands with `docker compose exec web python manage.py …` and copy the files across.

1. Export the jobs that need a translation (`--job ID` re-exports one job):

   ```
   DJANGO_DEBUG=1 .venv311/Scripts/python.exe manage.py export_translations --limit 20 > <scratchpad>/translate-batch.jsonl
   ```

   An empty file means nothing is pending. Stop there and say so.

2. Split the batch into chunks of up to 5 lines (`translate-in-1.jsonl`, `translate-in-2.jsonl`, …) and start one `translator` agent per chunk, all in the same message so they run in parallel. Give each the absolute input path and an absolute output path (`translate-out-N.jsonl`).

3. When they finish, import each output file:

   ```
   DJANGO_DEBUG=1 .venv311/Scripts/python.exe manage.py import_translations <scratchpad>/translate-out-N.jsonl --translator "claude-code haiku subagent"
   ```

   Each rejected line is reported with its reason. Fix the line yourself, or rerun a translator on that one job, but only with a fix that comes from the advert. A "text changed after export" rejection needs a fresh export.

4. Spot-check: read two or three imported versions against their source text (invented facts, wrong dates, Croatian or Serbian forms in Bosnian). Correct and reimport anything wrong.

5. Repeat from step 1 until the export is empty, or until the user's limit. Report how many were imported, rejected and corrected.
