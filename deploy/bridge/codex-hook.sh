#!/usr/bin/env bash
# Codex hooks.json command：自 stdin 讀取事件 JSON，寫入本機 Bridge Outbox。
# 不直送 CoreS3；Pi Coordinator 同步為下一項功能。
set -euo pipefail

STACKCHAN_BIN="${STACKCHAN_BIN:-stackchan}"
BRIDGE_ID="${STACKCHAN_BRIDGE_ID:-bridge_primary}"
DB="${STACKCHAN_BRIDGE_DB:-${HOME}/.stackchan/bridge.sqlite3}"

mkdir -p "$(dirname "$DB")"
exec "$STACKCHAN_BIN" bridge ingest-hook \
  --db "$DB" \
  --bridge-id "$BRIDGE_ID" \
  --adapter codex \
  --stdin
