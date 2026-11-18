#!/usr/bin/env bash
# Codex legacy notify wrapper：最後一個 argv 為事件 JSON。
# 不直送 CoreS3；只寫本機 Bridge Outbox。
set -euo pipefail

STACKCHAN_BIN="${STACKCHAN_BIN:-stackchan}"
BRIDGE_ID="${STACKCHAN_BRIDGE_ID:-bridge_primary}"
DB="${STACKCHAN_BRIDGE_DB:-${HOME}/.stackchan/bridge.sqlite3}"

if [[ $# -lt 1 ]]; then
  echo "error: Codex notify 未提供 JSON 參數" >&2
  exit 1
fi

JSON_PAYLOAD="${!#}"
mkdir -p "$(dirname "$DB")"
exec "$STACKCHAN_BIN" bridge ingest-hook \
  --db "$DB" \
  --bridge-id "$BRIDGE_ID" \
  --adapter codex \
  --argv-json "$JSON_PAYLOAD"
