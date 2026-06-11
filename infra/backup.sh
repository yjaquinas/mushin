#!/bin/bash
# infra/backup.sh — WAL-safe SQLite snapshot + retention rotation for Mushin.
#
# Run as the `mushin` service user (via mushin-backup.service, a oneshot
# triggered daily by mushin-backup.timer). Never copies the live -wal/-shm
# files directly — uses the SQLite `.backup` API via the `sqlite3` CLI, which
# is the WAL-safe equivalent of the Python sqlite3.Connection.backup() method.
#
# The resulting snapshot is a single consistent .db file that rclone can sync
# to off-host storage without any special handling.
set -euo pipefail

# ── Config — overridable via environment ───────────────────────────────
DB_PATH="${MUSHIN_DB_PATH:-/opt/mushin/data/app.db}"
BACKUP_DIR="${MUSHIN_BACKUP_DIR:-/opt/mushin/data/backups}"
RETENTION_COUNT="${MUSHIN_BACKUP_RETENTION:-7}"
DATE_STAMP="${MUSHIN_BACKUP_DATE_STAMP:-$(date -u +%Y%m%d-%H%M%S)}"
# ─────────────────────────────────────────────────────────────────────────

mkdir -p "$BACKUP_DIR"

DEST="$BACKUP_DIR/app-${DATE_STAMP}.db"

echo "[backup] snapshotting $DB_PATH -> $DEST"
sqlite3 "$DB_PATH" ".backup '$DEST'"

echo "[backup] verifying integrity of $DEST"
INTEGRITY_RESULT=$(sqlite3 "$DEST" "PRAGMA integrity_check;")
if [[ "$INTEGRITY_RESULT" != "ok" ]]; then
    echo "[backup] FATAL: integrity_check failed for $DEST: $INTEGRITY_RESULT" >&2
    rm -f "$DEST"
    exit 1
fi
echo "[backup] integrity_check ok"

# ── Rotation: keep the newest $RETENTION_COUNT snapshots, delete the rest ──
echo "[backup] rotating snapshots in $BACKUP_DIR (keeping $RETENTION_COUNT)"
mapfile -t SNAPSHOTS < <(find "$BACKUP_DIR" -maxdepth 1 -name 'app-*.db' -type f | sort -r)
if [[ "${#SNAPSHOTS[@]}" -gt "$RETENTION_COUNT" ]]; then
    for old in "${SNAPSHOTS[@]:$RETENTION_COUNT}"; do
        echo "[backup] removing old snapshot $old"
        rm -f "$old"
    done
fi

echo "[backup] done. $(find "$BACKUP_DIR" -maxdepth 1 -name 'app-*.db' -type f | wc -l) snapshot(s) retained."
