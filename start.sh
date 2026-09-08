#!/usr/bin/env bash
set -euo pipefail

# Render/Railway/Fly provide PORT. Local fallback is 8901.
PORT="${PORT:-8901}"
HOST="${HOST:-0.0.0.0}"

exec uvicorn main:app --host "$HOST" --port "$PORT"
