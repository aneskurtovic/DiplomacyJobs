#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

app_dir=/opt/diplomacyjobs
backup="${1:?Pass a custom-format backup file}"
test -s "$backup" || { echo "Backup is missing or empty" >&2; exit 1; }
cd "$app_dir"
db_password="$(sed -n 's/^POSTGRES_PASSWORD=//p' .env)"
test -n "$db_password" || { echo "Missing database password" >&2; exit 1; }

scratch="diplomacyjobs_restore_$(date -u +%Y%m%d%H%M%S)_$$"
cleanup() {
    docker exec ludo-postgres dropdb -U ludonexus --if-exists --force "$scratch"
}
trap cleanup EXIT
docker exec ludo-postgres createdb -U ludonexus -O diplomacyjobs "$scratch"
docker exec -i -e PGPASSWORD="$db_password" ludo-postgres \
    pg_restore -h 127.0.0.1 -U diplomacyjobs --no-owner --no-acl \
    --single-transaction --exit-on-error -d "$scratch" < "$backup"
actual="$(docker exec -e PGPASSWORD="$db_password" ludo-postgres \
    psql -h 127.0.0.1 -U diplomacyjobs -d "$scratch" -Atqc \
    'SELECT count(*) FROM board_source')"
expected="$(docker exec -e PGPASSWORD="$db_password" ludo-postgres \
    psql -h 127.0.0.1 -U diplomacyjobs -d diplomacyjobs -Atqc \
    'SELECT count(*) FROM board_source')"
test "$actual" = "$expected" || {
    echo "Restored $actual sources; production has $expected" >&2
    exit 1
}
echo "Restore verified in scratch database: $actual sources"
