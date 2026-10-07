#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

app_dir=/opt/diplomacyjobs
cd "$app_dir"
test -d .git || { echo "Clone the repository into $app_dir first" >&2; exit 1; }
if [[ -e .env ]]; then
    echo "Existing .env kept"
    exit 0
fi

secret_key="$(openssl rand -hex 48)"
db_password="$(openssl rand -hex 32)"
cat > .env <<EOF
DJANGO_SECRET_KEY=$secret_key
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=poslovi.aneskurtovic.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://poslovi.aneskurtovic.com
DATABASE_URL=postgresql://diplomacyjobs:$db_password@db:5432/diplomacyjobs
POSTGRES_PASSWORD=$db_password
PUBLIC_BASE_URL=https://poslovi.aneskurtovic.com
DJANGO_SECURE_SSL_REDIRECT=0
DJANGO_HSTS_SECONDS=0
EOF
chmod 600 .env
echo "Created production .env with generated secrets"
