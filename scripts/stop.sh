#!/usr/bin/env bash
# Mail RAG Desktop — Sidecar / 開発プロセス停止
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_DIR="${ROOT}/.run"
SIDECAR_PORT="${MAILRAG_PORT:-18765}"
VITE_PORT="${MAILRAG_VITE_PORT:-1420}"

log() { printf '[mailrag] %s\n' "$*"; }

stop_pidfile() {
  local file="$1"
  local label="$2"
  if [[ -f "${file}" ]]; then
    local pid
    pid="$(cat "${file}" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      log "${label} を停止します (pid=${pid})"
      kill "${pid}" 2>/dev/null || true
      sleep 0.3
      kill -9 "${pid}" 2>/dev/null || true
    fi
    rm -f "${file}"
  fi
}

stop_port() {
  local port="$1"
  local label="$2"
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "${pids}" ]]; then
      log "${label}（ポート ${port}）を停止します: ${pids}"
      # shellcheck disable=SC2086
      kill ${pids} 2>/dev/null || true
      sleep 0.3
      # shellcheck disable=SC2086
      kill -9 ${pids} 2>/dev/null || true
    fi
  fi
}

stop_pidfile "${PID_DIR}/sidecar.pid" "Sidecar"
stop_port "${SIDECAR_PORT}" "Sidecar"
stop_port "${VITE_PORT}" "Vite"

log "停止処理が完了しました"
