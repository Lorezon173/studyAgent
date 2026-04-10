#!/usr/bin/env bash

set -euo pipefail

cleanup() {
  if [[ -n "${backend_pid:-}" ]]; then
    kill "${backend_pid}" 2>/dev/null || true
  fi

  if [[ -n "${chainlit_pid:-}" ]]; then
    kill "${chainlit_pid}" 2>/dev/null || true
  fi

  wait 2>/dev/null || true
}

trap cleanup INT TERM EXIT

uv run uvicorn app.main:app --host 0.0.0.0 --port 1900 --reload &
backend_pid=$!

uv run chainlit run app/ui/chainlit_app.py --host 0.0.0.0 --port 2554 -w &
chainlit_pid=$!

wait -n "${backend_pid}" "${chainlit_pid}"
exit_code=$?

cleanup
exit "${exit_code}"