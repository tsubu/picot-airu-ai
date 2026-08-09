#!/usr/bin/env bash
# Build Python Sidecar binary for Tauri externalBin
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/python"

if [[ ! -x .venv/bin/python && ! -x .venv/Scripts/python.exe ]]; then
  echo "[build_sidecar] creating venv..."
  python3 -m venv .venv
fi

if [[ -x .venv/bin/python ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  PY=python
else
  PY=".venv/Scripts/python.exe"
fi

"$PY" -m pip install -q -U pip
"$PY" -m pip install -q -r requirements.txt pyinstaller

TRIPLE="$("$PY" - <<'PY'
import sys
import platform
osname = sys.platform
machine = platform.machine().lower()
if osname == "darwin":
    arch = "aarch64" if machine in ("arm64", "aarch64") else "x86_64"
    print(f"{arch}-apple-darwin")
elif osname == "win32":
    arch = "aarch64" if machine in ("arm64", "aarch64") else "x86_64"
    print(f"{arch}-pc-windows-msvc")
else:
    arch = "aarch64" if machine in ("arm64", "aarch64") else "x86_64"
    print(f"{arch}-unknown-linux-gnu")
PY
)"

OUT_DIR="${ROOT}/desktop/src-tauri/binaries"
mkdir -p "${OUT_DIR}"
rm -rf build dist mailrag-sidecar.spec 2>/dev/null || true

echo "[build_sidecar] PyInstaller → mailrag-sidecar (${TRIPLE})"
"$PY" -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name mailrag-sidecar \
  --hidden-import keyring.backends \
  --hidden-import keyring.backends.macOS \
  --hidden-import keyring.backends.Windows \
  --hidden-import google.genai \
  sidecar.py

SRC="dist/mailrag-sidecar"
if [[ -f "dist/mailrag-sidecar.exe" ]]; then
  SRC="dist/mailrag-sidecar.exe"
fi

DEST="${OUT_DIR}/mailrag-sidecar-${TRIPLE}"
if [[ "${SRC}" == *.exe ]]; then
  DEST="${DEST}.exe"
fi
cp "${SRC}" "${DEST}"
chmod +x "${DEST}" || true

# Convenience copy without triple (local spawn fallback)
if [[ "${DEST}" == *.exe ]]; then
  cp "${DEST}" "${OUT_DIR}/mailrag-sidecar.exe"
else
  cp "${DEST}" "${OUT_DIR}/mailrag-sidecar"
  chmod +x "${OUT_DIR}/mailrag-sidecar"
fi

ls -lh "${OUT_DIR}"
echo "[build_sidecar] done: ${DEST}"
