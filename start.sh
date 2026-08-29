#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
PYTHON="${PWD}/.venv/bin/python"
URL="http://127.0.0.1:8000"

if [[ ! -x "${PYTHON}" ]]; then
  echo "[ERROR] Virtual environment not found: ${PYTHON}" >&2
  echo "Create it first with: python3.11 -m venv .venv" >&2
  exit 1
fi

mkdir -p cache reports logs

if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 2 "${URL}/health" >/dev/null 2>&1; then
  echo "Platform is already running at ${URL}"
  if command -v xdg-open >/dev/null 2>&1; then xdg-open "${URL}" >/dev/null 2>&1 & fi
  exit 0
fi

echo "Starting AKShare Technical Analyzer at ${URL}"
if command -v xdg-open >/dev/null 2>&1; then
  (sleep 2; xdg-open "${URL}") >/dev/null 2>&1 &
fi
exec "${PYTHON}" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
