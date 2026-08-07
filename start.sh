#!/usr/bin/env bash
# リポジトリルートから起動するショートカット
exec "$(cd "$(dirname "$0")" && pwd)/scripts/start.sh" "$@"
