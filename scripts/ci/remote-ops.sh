#!/usr/bin/env bash
# Allow-listed maintenance tasks on the deployed app, installed root-owned as /opt/diplomacyjobs-ops.sh.
# Runs against the containers as deployed; it never checks out or builds code.
set -Eeuo pipefail

task="${1:?pass a task name}"
arg="${2:-}"
[[ -z "$arg" || "$arg" =~ ^[0-9]{1,6}$ ]] || { echo "The argument must be a number" >&2; exit 2; }

app_dir=/opt/diplomacyjobs
cd "$app_dir"
# The deploy holds the same lock, so a task never runs against a half-restarted app.
exec 9>/tmp/diplomacyjobs-deploy.lock
flock 9

compose=(docker compose -f compose.prod.yaml)
web() { "${compose[@]}" exec -T web python manage.py "$@"; }
# Scrapes run in the scraper container, which holds the scrape lock of the daily run.
scraper() { "${compose[@]}" exec -T scraper python manage.py "$@"; }
backup() { "$app_dir/scripts/ci/backup-db.sh"; }
no_arg() { [[ -z "$arg" ]] || { echo "$task takes no argument" >&2; exit 2; }; }

echo "Ops task: $task${arg:+ $arg} at $(git rev-parse --short HEAD)"
case "$task" in
    extract_requirements_dry_run) no_arg; web extract_requirements --dry-run ;;
    extract_requirements) no_arg; backup; web extract_requirements ;;
    reconcile_duplicates) no_arg; backup; web reconcile_duplicates ;;
    import_registry) no_arg; backup; web import_registry ;;
    verify_sources) no_arg; web verify_sources ;;
    scrape)
        backup
        if [[ -n "$arg" ]]; then scraper scrape_jobs --source "$arg"; else scraper scrape_jobs; fi ;;
    history)
        [[ "$arg" =~ ^20[0-9]{2}$ ]] || { echo "history needs a year, e.g. history-2025" >&2; exit 2; }
        backup; scraper scrape_jobs --history "$arg" ;;
    *) echo "Unknown task: $task" >&2; exit 2 ;;
esac
echo "Ops task $task finished"
