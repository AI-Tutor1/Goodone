# Runbook — Disaster Recovery

What to do when things go wrong. Severity-tiered. Run through this once during Phase 6 acceptance even if nothing's broken — finding out the backup is unrestoreable during an actual incident is the worst time to discover it.

## Severity tiers

- **SEV-1 — Data loss or corruption:** ledger inconsistent, DB corruption, restore needed. Pages CFO immediately.
- **SEV-2 — System down:** users cannot access; no data lost. Page CFO if business hours; queue overnight if not.
- **SEV-3 — Single feature broken:** ingestion stalled, report not generating. Resolve next business day.
- **SEV-4 — Cosmetic / minor:** typo in report, layout glitch. Track in normal backlog.

## SEV-1 — Data loss / corruption

### Symptoms
- Sub-ledger does not reconcile to GL after running daily check
- DB queries return inconsistent results
- Backup verification reports mismatched checksums
- Files in object storage missing referenced from JEs

### Immediate steps
1. **Stop writes.** Bring the FastAPI service down: `sudo systemctl stop tuitional-api`. This prevents further damage.
2. **Snapshot current state.** Even if corrupt, capture it for forensic review:
   ```
   pg_dump tuitional > /var/backups/forensic_$(date +%Y%m%d_%H%M%S).sql
   ```
3. **Identify scope.** What's wrong, since when, what data is affected? Audit log + period_close_log are the starting points.
4. **Decide: restore from backup vs. forward-fix.**
   - Restore: any time the corruption window > a few hours OR the integrity is unclear
   - Forward-fix: small, well-understood error (one wrong JE) → reverse + re-post

### Restore from backup
Backups are in `/var/backups/tuitional/` on the VPS (and replicated offsite per your setup):
- Daily logical dumps: 30-day retention
- Hourly WAL archives: 14-day retention (point-in-time recovery)
- Weekly full physical backups: 12-week retention

Steps:
1. `sudo systemctl stop tuitional-api tuitional-agents`
2. Identify target restore point: `ls /var/backups/tuitional/`
3. `dropdb tuitional && createdb tuitional`
4. `psql tuitional < /var/backups/tuitional/daily_YYYY-MM-DD.sql`
5. For point-in-time after a daily dump:
   - Replay WAL up to target time per Postgres docs
6. Verify: `psql tuitional -c "SELECT period, status FROM periods ORDER BY period DESC LIMIT 5"`
7. Run integrity checks: `tuitional verify-integrity --full`
8. Bring services back up: `sudo systemctl start tuitional-api tuitional-agents`
9. Run a smoketest pass: `make smoketest`
10. Notify users; explain the lost transactions (everything between the restore point and the incident); plan to re-ingest.

### Re-ingest after restore
- LMS sessions: re-pull from LMS API for the affected date range. Idempotency keys prevent duplicates with anything that survived restore.
- Bank statements: re-upload CSVs.
- Manual JEs by CFO: have to be manually re-entered. CFO should keep records.
- Sanction approvals: any pending may need re-doing if their state was lost.

## SEV-2 — System down

### Symptoms
- Dashboard returns 500 or fails to load
- API endpoints all error
- Database connections refused

### Steps
1. Check service status: `sudo systemctl status tuitional-api tuitional-agents postgresql`
2. Check logs: `journalctl -u tuitional-api -n 200 --no-pager`
3. Common causes:
   - Out of disk: `df -h`. If >90%, rotate logs, prune old backups.
   - Postgres down: `sudo systemctl restart postgresql`. Check connection limits, RAM.
   - Memory exhaustion: `free -h`. Check if Python services are leaking; restart.
   - Network: VPS provider issue; check status page.
4. Restart services if cause is transient: `sudo systemctl restart tuitional-api`.
5. If issue persists: compare against last working state. Recent deploy? Roll back.

## SEV-3 — Single feature broken

### Examples and fixes

**Ingestion stalled (LMS)**
- Check `audit_log` for the adapter's last successful run
- Check LMS API health
- Trigger manual re-run: Dashboard → Ingestion → LMS → Run

**FX rates not updating**
- exchangerate.host might be down
- Manually override today's rate per `fx_rate_override.md`
- File a ticket if API is down > 24 hours

**Report not generating**
- Re-run the Reporting Agent: Dashboard → Period → Re-run Reports
- Check logs for errors

**Email approval link not working**
- Token may be expired (>7 days)
- Resend from Sanctions → request → "Resend approval link"

## Backups verification

This should happen automatically every day. The CI/CD pipeline (or a cron) restores last night's backup to a scratch DB and runs smoketest checks. Any failure raises an alert.

Manual verification (do this Phase 6 acceptance, then quarterly):
```bash
# On a test VPS or local machine
createdb tuitional_restore_test
psql tuitional_restore_test < /var/backups/tuitional/daily_YYYY-MM-DD.sql
tuitional verify-integrity --full
dropdb tuitional_restore_test
```

If verify-integrity fails → backup is bad → escalate immediately.

## Communications

For SEV-1 / SEV-2 affecting the CFO's ability to work:
- Notify CFO via SMS/call (out-of-band; email may be down)
- Brief written update every 30 minutes during incident
- Post-incident review document within 48 hours

## Post-incident review template

After every SEV-1 or SEV-2:

```
Date:
Severity:
Duration:
Detected by:
Root cause:
Resolution:
Data impact:
Customer/CFO impact:
Action items (with owners and due dates):
```

Filed under `docs/incidents/YYYY-MM-DD-summary.md` (this directory created on first incident).

## Drills

Phase 6 acceptance includes:
1. Restore-from-backup drill (full)
2. Recovery-from-corruption drill (forced corruption then forward-fix)
3. SEV-2 simulation (kill services, recover)

These are walked through with the CFO present. The first time we do this in production, the CFO sees the full process; after that, they trust it.
