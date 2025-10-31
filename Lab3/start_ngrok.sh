#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8080}"

if ! command -v ngrok >/dev/null 2>&1; then
  echo "ngrok is not installed or not in PATH. See https://ngrok.com/download" >&2
  exit 1
fi

echo "Starting ngrok http ${PORT} ..."
exec ngrok http "${PORT}"

