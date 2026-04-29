#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${AVA_DEVICEKIT_ENV_FILE:-$ROOT/ava-devicekit/.env.local}"
CONFIG_FILE="${AVA_DEVICEKIT_RUNTIME_CONFIG:-/tmp/ava_devicekit_runtime.real.json}"
SKILL_STORE="${AVA_DEVICEKIT_SKILL_STORE:-$ROOT/data/ava_box_app_state.json}"
HOST="${AVA_DEVICEKIT_HOST:-127.0.0.1}"
HTTP_PORT="${AVA_DEVICEKIT_HTTP_PORT:-8788}"
WS_PORT="${AVA_DEVICEKIT_WS_PORT:-8787}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  echo "warning: env file not found: $ENV_FILE" >&2
fi

cd "$ROOT"
PYTHONPATH="$ROOT/ava-devicekit/backend${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m ava_devicekit.cli run-server \
    --host "$HOST" \
    --port "$HTTP_PORT" \
    --ws-port "$WS_PORT" \
    --config "$CONFIG_FILE" \
    --skill-store "$SKILL_STORE"
