#!/bin/bash
set -euo pipefail

WATCH_DIR="/var/recordings/NODE_NUMBER"
REMOTE_USER="USER"
REMOTE_HOST="HOST NAME / IP"   # <-- set this
REMOTE_DIR="FOLDER TO SFTP TO"
SSH_PORT="22"

log(){ printf '[%(%F %T)T] %s\n' -1 "$*" >&2; }

send_file() {
  local f="$1"
  local base tmp
  base="$(basename "$f")"
  tmp="${base}.part"

  # upload to .part then atomically rename
  if sftp -oBatchMode=yes -P "$SSH_PORT" "${REMOTE_USER}@${REMOTE_HOST}" <<SFTP_CMDS
cd ${REMOTE_DIR}
put -p "$f" "$tmp"
rename "$tmp" "$base"
SFTP_CMDS
  then
    log "Uploaded: $base"
    rm -f -- "$f" || true
  else
    log "ERROR uploading: $base (will retry later)"
    return 1
  fi
}

# initial sweep (anything leftover)
shopt -s nullglob
for f in "${WATCH_DIR}"/*.WAV; do
  if ! lsof -t -- "$f" >/dev/null 2>&1; then
    send_file "$f" || true
  fi
done

log "Watching ${WATCH_DIR} for completed WAVs..."
inotifywait -m -e close_write --format '%w%f' "$WATCH_DIR" \
| while read -r f; do
    [[ "${f,,}" == *.WAV ]] || continue
    sleep 0.2
    send_file "$f" || true
  done