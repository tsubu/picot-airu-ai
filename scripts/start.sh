#!/usr/bin/env bash
# Mail RAG Desktop — 開発起動（Sidecar + Desktop）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SIDECAR_PORT="${MAILRAG_PORT:-18765}"
SIDECAR_URL="http://127.0.0.1:${SIDECAR_PORT}"
PID_DIR="${ROOT}/.run"
SIDECAR_PID_FILE="${PID_DIR}/sidecar.pid"
MODE="${1:-tauri}" # tauri | web | sidecar

mkdir -p "${PID_DIR}"

log() { printf '[mailrag] %s\n' "$*"; }
err() { printf '[mailrag] ERROR: %s\n' "$*" >&2; }

ensure_python() {
  if [[ ! -x "${ROOT}/python/.venv/bin/python" ]]; then
    err "python/.venv がありません。先に ./scripts/setup.sh を実行してください。"
    exit 1
  fi
}

ensure_node() {
  if [[ ! -d "${ROOT}/desktop/node_modules" ]]; then
    err "desktop/node_modules がありません。先に ./scripts/setup.sh を実行してください。"
    exit 1
  fi
}

sidecar_healthy() {
  curl -sf "${SIDECAR_URL}/health" >/dev/null 2>&1
}

start_sidecar() {
  if sidecar_healthy; then
    log "Sidecar は既に起動中です (${SIDECAR_URL})"
    return 0
  fi

  ensure_python
  log "Sidecar を起動します (${SIDECAR_URL})"
  (
    cd "${ROOT}/python"
    # shellcheck disable=SC1091
    source .venv/bin/activate
    exec python sidecar.py "${SIDECAR_PORT}"
  ) >"${PID_DIR}/sidecar.log" 2>&1 &
  echo $! >"${SIDECAR_PID_FILE}"

  for _ in $(seq 1 40); do
    if sidecar_healthy; then
      log "Sidecar 起動完了 (pid=$(cat "${SIDECAR_PID_FILE}"))"
      return 0
    fi
    sleep 0.25
  done

  err "Sidecar の起動に失敗しました。ログ: ${PID_DIR}/sidecar.log"
  tail -n 40 "${PID_DIR}/sidecar.log" >&2 || true
  exit 1
}

cleanup() {
  # Tauri/Vite 終了時に、このスクリプトが起動した Sidecar だけ止める
  if [[ -f "${SIDECAR_PID_FILE}" ]]; then
    local pid
    pid="$(cat "${SIDECAR_PID_FILE}" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      log "Sidecar を停止します (pid=${pid})"
      kill "${pid}" 2>/dev/null || true
      wait "${pid}" 2>/dev/null || true
    fi
    rm -f "${SIDECAR_PID_FILE}"
  fi
}

case "${MODE}" in
  -h|--help|help)
    cat <<EOF
Usage: ./scripts/start.sh [tauri|web|sidecar]

  tauri    Sidecar + Tauri デスクトップアプリ（既定）
  web      Sidecar + Vite フロントのみ（ブラウザ）
  sidecar  Sidecar のみ起動

停止: ./scripts/stop.sh
初回: ./scripts/setup.sh
EOF
    exit 0
    ;;
  sidecar)
    start_sidecar
    log "Sidecar のみ起動中。停止は ./scripts/stop.sh"
    # フォアグラウンドでログを見せつつ待ち受け
    if [[ -f "${SIDECAR_PID_FILE}" ]]; then
      tail -f "${PID_DIR}/sidecar.log" &
      TAIL_PID=$!
      trap 'kill '"${TAIL_PID}"' 2>/dev/null || true; cleanup' EXIT INT TERM
      wait "$(cat "${SIDECAR_PID_FILE}")" 2>/dev/null || true
    fi
    ;;
  web)
    ensure_node
    start_sidecar
    trap cleanup EXIT INT TERM
    log "Vite を起動します (http://localhost:1420)"
    cd "${ROOT}/desktop"
    npm run dev
    ;;
  tauri|*)
    ensure_node
    start_sidecar
    trap cleanup EXIT INT TERM
    log "Tauri アプリを起動します"
    cd "${ROOT}/desktop"
    # Tauri 側でも Sidecar 起動を試すが、先に起動済みなら health で再利用される
    export MAILRAG_PYTHON="${ROOT}/python/.venv/bin/python"
    export MAILRAG_SIDECAR="${ROOT}/python/sidecar.py"
    npm run tauri dev
    ;;
esac
