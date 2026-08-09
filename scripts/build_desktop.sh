#!/usr/bin/env bash
# Build Picot AIRU AI desktop bundles (.app / .dmg / .exe / .msi)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODE="${1:-local}" # local | skip-sidecar

if [[ "${MODE}" != "skip-sidecar" ]]; then
  bash "${ROOT}/scripts/build_sidecar.sh"
fi

BIN_DIR="${ROOT}/desktop/src-tauri/binaries"
if ! ls "${BIN_DIR}"/mailrag-sidecar* >/dev/null 2>&1; then
  echo "[build_desktop] ERROR: sidecar binary missing in ${BIN_DIR}" >&2
  echo "Run ./scripts/build_sidecar.sh first, or pass skip-sidecar only when binaries exist." >&2
  exit 1
fi

cd "${ROOT}/desktop"
if [[ ! -d node_modules ]]; then
  npm ci || npm install
fi

echo "[build_desktop] tauri build..."
npm run tauri -- build

echo "[build_desktop] artifacts:"
find src-tauri/target/release/bundle -type f \( -name "*.dmg" -o -name "*.app" -o -name "*.exe" -o -name "*.msi" -o -name "*.deb" -o -name "*.AppImage" \) 2>/dev/null | sort || true
# .app is a directory
find src-tauri/target/release/bundle -type d -name "*.app" 2>/dev/null | sort || true
