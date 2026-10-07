import json
import re
from datetime import date
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from board import requirements
from board.ingest import DATE_TEXT, parse_date
from board.models import Job

FACT_FIELDS = {"title", "city", "deadline", "application_url"}
REQUIREMENT_FIELDS = set(requirements.PROTECTABLE)
EMPTY = (None, "", [])


def requirement_value(field, value, quote):
    """A proposed requirement field, checked against its quote. The quote may be in any language, so only what can be checked is."""
    if field == "education_level":
        if value not in requirements.LEVEL_RANK:
            raise ValueError("invalid education_level")
        # Where the rules recognise a level in the quote, the proposal must be one of those levels.
        stated = {level for level, pattern in requirements.LEVEL_PATTERNS.items() if pattern.search(quote)}
        if stated and value not in stated:
            raise ValueError("education_level not in its evidence")
    elif field == "experience_years":
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 30:
            raise ValueError("invalid experience_years")
        numbers = {requirements.number(token) for token in re.findall(requirements.NUMBER, quote, re.I)}
        if value and value not in numbers:
            raise ValueError("experience_years not in its evidence")
    else:
        if not isinstance(value, list) or not value or len(value) > 4 or len(set(value)) != len(value) or not set(value) <= set(requirements.FIELD_LABELS):
            raise ValueError("invalid fields_of_study")
    return value


class Command(BaseCommand):
    help = "Validate and import optional AI suggestions; conflicts stay in review"

    def add_arguments(self, parser):
        parser.add_argument("path")

    @transaction.atomic
    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.is_file():
            raise CommandError(f"File missing: {path}")
        applied = 0
        rejected = 0
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                item = json.loads(line)
                job = Job.objects.select_for_update().get(pk=item["id"])
                if item["content_hash"] != job.content_hash:
                    raise ValueError("stale source content")
                proposals = item["proposed"]
                evidence = item["evidence"]
                if not isinstance(proposals, dict) or not set(proposals) <= FACT_FIELDS | REQUIREMENT_FIELDS or not isinstance(evidence, dict):
                    raise ValueError("invalid field set")
                changes = {}
                for field, value in proposals.items():
                    quote = evidence.get(field, "")
                    if not isinstance(quote, str) or len(quote) < 3 or quote.casefold() not in job.raw_text.casefold():
                        raise ValueError(f"unsupported {field}")
                    if field in job.manually_edited_fields:
                        raise ValueError(f"manual value for {field}")
                    if field in REQUIREMENT_FIELDS:
                        value = requirement_value(field, value, quote)
                    elif field == "deadline":
                        value = date.fromisoformat(value) if value else None
                    elif not isinstance(value, str) or len(value) > (1000 if field == "application_url" else 100 if field == "city" else 400):
                        raise ValueError(f"invalid {field}")
                    if field == "application_url" and value and not value.startswith("https://"):
                        raise ValueError("application URL must be HTTPS")
                    # The quote must back the value itself, not merely exist in the source. Titles may be translated, so only facts are checked.
                    if field == "deadline" and value and value not in {parse_date(match.group(0)) for match in re.finditer(DATE_TEXT, quote, re.I)}:
                        raise ValueError("deadline not in its evidence")
                    if field in ("city", "application_url") and value and value.casefold() not in quote.casefold():
                        raise ValueError(f"{field} not in its evidence")
                    old = getattr(job, field)
                    if old not in EMPTY and old != value:
                        raise ValueError(f"conflicting {field}")
                    changes[field] = value
                for field, value in changes.items():
                    setattr(job, field, value)
                    job.field_evidence[field] = evidence[field]
                job.field_evidence["ai_fields"] = sorted(set(job.field_evidence.get("ai_fields", [])) | set(changes))
                job.save()
                applied += 1
            except (KeyError, ValueError, TypeError, Job.DoesNotExist) as exc:
                rejected += 1
                self.stderr.write(f"line {line_number}: {exc}")
        self.stdout.write(f"Applied {applied}; rejected {rejected}")
