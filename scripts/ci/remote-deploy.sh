#!/usr/bin/env bash
set -Eeuo pipefail

sha="${1:?pass the full commit SHA}"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo "Expected a full commit SHA" >&2; exit 2; }

app_dir=/opt/diplomacyjobs
cd "$app_dir"
exec 9>/tmp/diplomacyjobs-deploy.lock
flock 9

test -f .env || { echo "Missing $app_dir/.env" >&2; exit 1; }
git diff --quiet && git diff --cached --quiet || { echo "Server checkout has local changes" >&2; exit 1; }
git fetch --prune origin main
git cat-file -e "$sha^{commit}"
git merge-base --is-ancestor "$sha" origin/main || { echo "Commit is not on origin/main" >&2; exit 1; }

compose=(docker compose -f compose.prod.yaml)
git checkout --detach "$sha"
"$app_dir/scripts/ci/backup-db.sh"
"${compose[@]}" config --quiet
"${compose[@]}" build web
"${compose[@]}" up -d --no-build web scraper

for attempt in $(seq 1 30); do
    if curl --fail --silent --show-error -H 'Host: poslovi.aneskurtovic.com' \
        http://127.0.0.1:8000/health/ > /dev/null 2>&1; then
        "${compose[@]}" exec -T web python manage.py check
        echo "Deployed $sha"
        exit 0
    fi
    sleep 2
done
"${compose[@]}" ps
"${compose[@]}" logs --tail=80 web
echo "Web health check did not pass" >&2
exit 1
