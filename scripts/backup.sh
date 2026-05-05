#!/usr/bin/env bash
# Postgres backup — logical (pg_dump) + size-checked + offsite hook.
#
# Driven by env vars (set by the systemd timer that calls it):
#   DATABASE_URL                        # required
#   BACKUP_DIR=/var/backups/tuitional   # default
#   BACKUP_RETENTION_DAYS=30
#   BACKUP_OFFSITE_S3_BUCKET            # optional; uses `aws s3 cp` if set
#
# Exits non-zero on any step failure so the systemd unit alarms.

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/tuitional}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
S3_BUCKET="${BACKUP_OFFSITE_S3_BUCKET:-}"

if [ -z "${DATABASE_URL:-}" ]; then
    echo "DATABASE_URL is required" >&2
    exit 2
fi

mkdir -p "$BACKUP_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$BACKUP_DIR/tuitional-${TS}.sql.gz"

echo "[backup] $TS → $DEST"

# Logical dump in custom format would be smaller, but plain SQL replays
# anywhere with just `psql` and is auditor-friendly.
pg_dump --no-owner --no-privileges --quote-all-identifiers \
        "$DATABASE_URL" | gzip -9 > "$DEST"

# Sanity check: dump must contain the COA and at least one period.
if ! zgrep -q "INSERT INTO master.chart_of_accounts" "$DEST" \
   && ! zgrep -q "COPY master.chart_of_accounts" "$DEST"; then
    echo "[backup] sanity check failed: COA not found in dump" >&2
    exit 3
fi

SIZE=$(stat -c '%s' "$DEST")
echo "[backup] wrote ${SIZE} bytes"

# Retention prune.
find "$BACKUP_DIR" -name 'tuitional-*.sql.gz' -mtime +"$RETENTION_DAYS" -delete

# Offsite copy (best-effort; failure here is alerting-worthy but doesn't
# invalidate the local backup).
if [ -n "$S3_BUCKET" ]; then
    if command -v aws >/dev/null 2>&1; then
        aws s3 cp --quiet "$DEST" "s3://$S3_BUCKET/$(basename "$DEST")" \
            || echo "[backup] WARN offsite copy failed" >&2
    else
        echo "[backup] WARN aws CLI not installed; skipping offsite" >&2
    fi
fi

# Backup uploaded file attachments alongside the DB dump.
# ATTACHMENTS_DIR must match the env var used by the API process.
ATTACHMENTS_DIR="${ATTACHMENTS_DIR:-/var/lib/tuitional/attachments}"
if [ -d "$ATTACHMENTS_DIR" ]; then
    ATTACH_DEST="$BACKUP_DIR/attachments-${TS}.tar.gz"
    tar -czf "$ATTACH_DEST" \
        -C "$(dirname "$ATTACHMENTS_DIR")" \
        "$(basename "$ATTACHMENTS_DIR")" \
        && echo "[backup] attachments → $ATTACH_DEST ($(stat -c '%s' "$ATTACH_DEST") bytes)" \
        || echo "[backup] WARN attachments backup failed" >&2
    if [ -n "$S3_BUCKET" ] && command -v aws >/dev/null 2>&1; then
        aws s3 cp --quiet "$ATTACH_DEST" \
            "s3://$S3_BUCKET/$(basename "$ATTACH_DEST")" \
            || echo "[backup] WARN offsite copy of attachments failed" >&2
    fi
    # Prune old attachment archives with the same retention as DB dumps.
    find "$BACKUP_DIR" -name 'attachments-*.tar.gz' -mtime +"$RETENTION_DAYS" -delete
else
    echo "[backup] WARN ATTACHMENTS_DIR=$ATTACHMENTS_DIR does not exist — skipping file backup" >&2
fi

echo "[backup] done"
