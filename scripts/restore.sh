#!/usr/bin/env bash
# Restore drill — pulls the most recent backup and replays it into a
# *separate* DB ("tuitional_restore"), then runs the reconciliation
# endpoint to confirm the GL still balances.
#
# This is the procedure documented in docs/runbooks/disaster_recovery.md.
# Run quarterly at minimum; the smoketest in CI exercises the same code
# path on every PR.

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/tuitional}"
TARGET_DATABASE_URL="${TARGET_DATABASE_URL:?set TARGET_DATABASE_URL pointing at the restore DB}"

LATEST="$(ls -1t "$BACKUP_DIR"/tuitional-*.sql.gz 2>/dev/null | head -n1 || true)"
if [ -z "$LATEST" ]; then
    echo "[restore] no backups found in $BACKUP_DIR" >&2
    exit 2
fi
echo "[restore] using $LATEST → $TARGET_DATABASE_URL"

# Apply schemas (init.sql is the source of truth for the seven schemas).
psql "$TARGET_DATABASE_URL" < "$(dirname "$0")/../infra/postgres/init.sql"

# Apply the dump.
gunzip -c "$LATEST" | psql "$TARGET_DATABASE_URL" >/dev/null

# Sanity check: trial balance must equal zero in the restored DB.
PSQL_OUT="$(psql "$TARGET_DATABASE_URL" -At -c "
  SELECT
    (SELECT COALESCE(SUM(debit_aed),0) FROM ledger.journal_lines)
    -
    (SELECT COALESCE(SUM(credit_aed),0) FROM ledger.journal_lines);
")"

if [ "$PSQL_OUT" != "0.00" ] && [ "$PSQL_OUT" != "0" ]; then
    echo "[restore] FAIL: trial balance after restore is $PSQL_OUT" >&2
    exit 3
fi

echo "[restore] OK: trial balance is zero in restored DB"
