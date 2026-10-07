#!/usr/bin/env bash
set -Eeuo pipefail

sha="${SSH_ORIGINAL_COMMAND:-}"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo "Expected a full commit SHA" >&2; exit 2; }
exec /opt/diplomacyjobs-deploy.sh "$sha"
