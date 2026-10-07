#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

app_dir=/opt/diplomacyjobs
cd "$app_dir"
install -d -m 700 "$app_dir/backups"

db_password="$(sed -n 's/^POSTGRES_PASSWORD=//p' .env)"
test -n "$db_password" || { echo "Missing database password" >&2; exit 1; }

backup="$app_dir/backups/diplomacyjobs-$(date -u +%Y%m%dT%H%M%SZ).dump"
temporary="$backup.partial"
trap 'rm -f "$temporary"' EXIT
docker exec -e PGPASSWORD="$db_password" ludo-postgres \
    pg_dump -h 127.0.0.1 -Fc -U diplomacyjobs diplomacyjobs > "$temporary"
docker exec -i ludo-postgres pg_restore -l < "$temporary" > /dev/null
mv "$temporary" "$backup"
find "$app_dir/backups" -maxdepth 1 -type f -name 'diplomacyjobs-*.dump' -mtime +30 -delete
echo "Database backup verified: $backup"
