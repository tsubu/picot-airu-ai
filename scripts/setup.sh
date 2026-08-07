#!/usr/bin/env bash
# Mail RAG Desktop — 初回セットアップ
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

log() { printf '[mailrag] %s\n' "$*"; }

log "Python venv を準備します"
if [[ ! -x python/.venv/bin/python ]]; then
  python3 -m venv python/.venv
fi
# shellcheck disable=SC1091
source python/.venv/bin/activate
pip install -U pip
pip install -r python/requirements.txt

log "desktop 依存関係をインストールします"
cd desktop
npm install
cd ..

mkdir -p .run
log "セットアップ完了"
log "起動: ./scripts/start.sh"
log "停止: ./scripts/stop.sh"
