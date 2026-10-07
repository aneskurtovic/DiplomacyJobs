#!/usr/bin/env bash
# Forced command of the Woodpecker ops SSH key: "<task> [number]" only.
set -Eeuo pipefail

read -r task arg extra <<< "${SSH_ORIGINAL_COMMAND:-}"
[[ "${task:-}" =~ ^[a-z_]{1,40}$ && -z "${extra:-}" && ( -z "${arg:-}" || "$arg" =~ ^[0-9]{1,6}$ ) ]] || { echo "Expected: <task> [number]" >&2; exit 2; }
exec /opt/diplomacyjobs-ops.sh "$task" ${arg:+"$arg"}
