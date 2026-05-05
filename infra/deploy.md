# VPS Deployment Runbook (Phase 6 final)

This is the step-by-step procedure for bringing Tuitional Finance up on a fresh **Ubuntu 24.04 LTS** VPS, end-to-end. You run this; the application is designed to be operator-managed. Estimated time end-to-end: 60–90 minutes.

The runbook assumes a single-VPS deployment with Postgres co-located. For HA / multi-region, see "Future hardening" at the bottom.

---

## 1. Provision

Pick a VPS with at minimum **2 vCPU, 4 GB RAM, 40 GB SSD**. Suggested providers: Hetzner CX22 (~€5/mo), DigitalOcean s-2vcpu-4gb, AWS t3.medium.

```bash
# On your laptop:
ssh root@<vps-ip>
# Create a non-root admin user.
adduser --gecos "" tuitional-admin
usermod -aG sudo tuitional-admin
rsync --archive --chown=tuitional-admin:tuitional-admin ~/.ssh /home/tuitional-admin
ssh-copy-id tuitional-admin@<vps-ip>
# Lock root SSH:
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl reload ssh
```

Reconnect as `tuitional-admin` and confirm `sudo -v` works.

---

## 2. System packages

```bash
sudo apt-get update
sudo apt-get install -y \
    postgresql-16 postgresql-contrib \
    nginx certbot python3-certbot-nginx \
    docker.io docker-compose-v2 \
    ufw fail2ban unattended-upgrades \
    git curl jq awscli
sudo systemctl enable --now docker postgresql nginx
sudo usermod -aG docker tuitional-admin
# log out and back in for the docker group to apply
```

Enable unattended security updates:

```bash
sudo dpkg-reconfigure -plow unattended-upgrades   # answer "yes"
```

UFW (only SSH + HTTPS open, plus Postgres on the loopback):

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

---

## 3. Application user + directories

```bash
sudo useradd --system --create-home --home-dir /opt/tuitional \
             --shell /usr/sbin/nologin tuitional
sudo install -d -o tuitional -g tuitional /var/lib/tuitional/attachments
sudo install -d -o tuitional -g tuitional /var/backups/tuitional
sudo install -d -o tuitional -g tuitional /etc/tuitional
```

Clone the repository (read-only token; we never run `git push` from prod):

```bash
sudo -u tuitional git clone https://github.com/<org>/tuitional-finance.git /opt/tuitional/app
sudo -u tuitional git -C /opt/tuitional/app checkout v0.6.0   # latest tagged release
```

---

## 4. Postgres

```bash
sudo -u postgres createuser --pwprompt tuitional   # set a strong password
sudo -u postgres createdb --owner=tuitional tuitional
sudo -u postgres psql -d tuitional \
    -f /opt/tuitional/app/infra/postgres/init.sql
```

Restrict listening to loopback only:

```bash
sudo sed -i "s/^#\?listen_addresses.*/listen_addresses = 'localhost'/" \
    /etc/postgresql/16/main/postgresql.conf
sudo systemctl restart postgresql
sudo -u postgres psql -c "SHOW listen_addresses"
```

---

## 5. Application configuration

Generate a secret key and store the production env file:

```bash
SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(64))')
CFO_PASSWORD=$(openssl rand -base64 24)

TOTP_SECRET=$(python3 -c 'import pyotp; print(pyotp.random_base32())')
FA_PASSWORD=$(openssl rand -base64 24)

sudo -u tuitional tee /etc/tuitional/app.env >/dev/null <<EOF
APP_ENV=production
APP_PORT=3002
DATABASE_URL=postgresql+psycopg://tuitional:<DB_PASSWORD>@localhost:5432/tuitional
SECRET_KEY=${SECRET}

# CFO auth + mandatory TOTP
CFO_USERNAME=cfo
CFO_PASSWORD=${CFO_PASSWORD}
CFO_TOTP_SECRET=${TOTP_SECRET}
TOTP_ENFORCED=true
CFO_EMAIL=cfo@your-domain.example

# Finance Admin (FA) role — can approve sanctions, view reports; cannot close periods
FA_USERNAME=fa
FA_PASSWORD=${FA_PASSWORD}
FA_EMAIL=fa@your-domain.example

LOG_FORMAT=json
LOG_LEVEL=INFO

# File uploads
ATTACHMENTS_DIR=/var/lib/tuitional/attachments
ATTACHMENTS_MAX_SIZE_MB=20

# Period close
PERIOD_CLOSE_AUTO_CLOSE_DAY=5

# Email
EMAIL_PROVIDER=smtp
SMTP_HOST=<your-smtp-host>
SMTP_PORT=587
SMTP_USERNAME=<smtp-user>
SMTP_PASSWORD=<smtp-pass>
EMAIL_FROM_ADDRESS=finance@your-domain.example
EMAIL_FROM_NAME=Tuitional Finance

# LMS (set when your LMS vendor provides API credentials)
# LMS_API_BASE_URL=https://lms.your-vendor.example
# LMS_API_KEY=<key>

# Google Sheets (set after uploading your service account JSON)
# GOOGLE_SERVICE_ACCOUNT_JSON_PATH=/etc/tuitional/google-sa.json
# GOOGLE_SHEETS_SESSIONS_ID=<spreadsheet-id>
# GOOGLE_SHEETS_ENROLLMENTS_ID=<spreadsheet-id>

# FX rates
# FX_API_KEY=<exchangerate.host key>
FX_BASE_CURRENCY=AED

# Anthropic CFO chat (optional — set CHAT_PROVIDER=anthropic to enable)
CHAT_PROVIDER=stub
# ANTHROPIC_API_KEY=<key>
EOF
sudo chown tuitional:tuitional /etc/tuitional/app.env
sudo chmod 600 /etc/tuitional/app.env
echo "Generated CFO password: $CFO_PASSWORD"
echo "Generated FA password:  $FA_PASSWORD"
echo "TOTP secret: $TOTP_SECRET"
echo ""
echo "IMPORTANT: Register the TOTP secret in an authenticator app (Google Authenticator / Authy)."
echo "Use this provisioning URI:"
python3 -c "
import pyotp, os
uri = pyotp.totp.TOTP(os.environ.get('TOTP_SECRET','${TOTP_SECRET}')).provisioning_uri('CFO', issuer_name='Tuitional Finance')
print(uri)
"
echo "Or use GET /auth/totp-setup after first login to display the QR code."
echo "Save CFO password, FA password, and TOTP secret in your password manager."
```

Backup environment:

```bash
sudo tee /etc/tuitional/backup.env >/dev/null <<'EOF'
DATABASE_URL=postgresql+psycopg://tuitional:<DB_PASSWORD>@localhost:5432/tuitional
BACKUP_DIR=/var/backups/tuitional
BACKUP_RETENTION_DAYS=30
BACKUP_OFFSITE_S3_BUCKET=
EOF
sudo chmod 600 /etc/tuitional/backup.env
```

---

## 6. Build and run the containers

```bash
cd /opt/tuitional/app
sudo docker build -f infra/docker/backend.Dockerfile -t tuitional-finance-backend:current .
sudo docker build -f infra/docker/frontend.Dockerfile -t tuitional-finance-frontend:current .
```

Install systemd units:

```bash
sudo install -m 644 infra/systemd/tuitional-api.service     /etc/systemd/system/
sudo install -m 644 infra/systemd/tuitional-worker.service  /etc/systemd/system/
sudo install -m 644 infra/systemd/tuitional-backup.service  /etc/systemd/system/
sudo install -m 644 infra/systemd/tuitional-backup.timer    /etc/systemd/system/
sudo install -m 755 scripts/backup.sh   /opt/tuitional/scripts/
sudo install -m 755 scripts/restore.sh  /opt/tuitional/scripts/
sudo systemctl daemon-reload
```

Apply the migration:

```bash
sudo -u tuitional sh -c '
    cd /opt/tuitional/app && \
    /usr/bin/env $(grep -v ^# /etc/tuitional/app.env | xargs) \
        /opt/tuitional/app/.venv/bin/alembic upgrade head'
```

Start the API and the backup timer:

```bash
sudo systemctl enable --now tuitional-api.service
sudo systemctl enable --now tuitional-backup.timer
sudo systemctl status tuitional-api
curl -fsS http://127.0.0.1:3002/healthz   # → {"status":"ok"}
```

---

## 7. Nginx + TLS

```bash
sudo tee /etc/nginx/sites-available/tuitional >/dev/null <<'EOF'
server {
    listen 80;
    server_name finance.your-domain.example;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name finance.your-domain.example;

    ssl_certificate     /etc/letsencrypt/live/finance.your-domain.example/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/finance.your-domain.example/privkey.pem;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Static frontend (built dist served from disk; or proxy the frontend container).
    root /opt/tuitional/app/frontend/dist;
    index index.html;

    location /api/ {
        proxy_pass         http://127.0.0.1:3002/;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri /index.html;
    }
}
EOF
sudo ln -sf /etc/nginx/sites-available/tuitional /etc/nginx/sites-enabled/tuitional
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d finance.your-domain.example --non-interactive --agree-tos -m ops@your-domain.example
```

The frontend dist is built once during install:

```bash
cd /opt/tuitional/app/frontend
sudo -u tuitional npm ci
sudo -u tuitional npm run build
```

---

## 8. Smoketest in production

```bash
# 1. Hit the public URL.
curl -fsS https://finance.your-domain.example/api/ | jq

# 2. Log in (replace with the password from step 5).
curl -c /tmp/cookies.txt -fsS -H 'Content-Type: application/json' \
    -X POST -d '{"username":"cfo","password":"<CFO_PASSWORD>"}' \
    https://finance.your-domain.example/api/auth/login

# 3. List periods (proves cookies + DB are wired).
curl -b /tmp/cookies.txt -fsS https://finance.your-domain.example/api/periods | jq

# 4. Run the smoketest harness against this DB.
cd /opt/tuitional/app
sudo -u tuitional sh -c '
    cd /opt/tuitional/app && \
    /usr/bin/env $(grep -v ^# /etc/tuitional/app.env | xargs) \
        /opt/tuitional/app/.venv/bin/pytest -m smoketest -q'
```

If the smoketest passes against production-shaped data, this gate is green.

---

## 9. Backup restore drill (do this BEFORE going live)

The drill confirms backups are real, not a directory full of corrupt blobs.

```bash
# Run a backup now.
sudo systemctl start tuitional-backup.service
sudo journalctl -u tuitional-backup.service --since "5 minutes ago" | tail

# Create a side-by-side restore DB.
sudo -u postgres createdb --owner=tuitional tuitional_restore

# Replay the latest backup into it.
sudo TARGET_DATABASE_URL="postgresql://tuitional:<DB_PASSWORD>@localhost:5432/tuitional_restore" \
    /opt/tuitional/scripts/restore.sh

# Tear down the drill.
sudo -u postgres dropdb tuitional_restore
```

Exit code 0 on `restore.sh` means the dump replays cleanly and the trial balance is zero. **This is the Phase-6 acceptance criterion**: "Backup restored to a fresh DB and ledger reconciles."

---

## 10. Observability

Prometheus pulls `https://finance.your-domain.example/api/metrics` every 30s. Grafana dashboards (out of scope here; templates ship in `infra/grafana/`) consume the metric names listed in `infra/prometheus/alerts.yml`. Logs go to journald and can be shipped to your aggregator of choice (Loki / OpenSearch / Cloudwatch — point its agent at `journalctl -fu tuitional-api`).

The alert rules in `infra/prometheus/alerts.yml` cover: backend down, high rejection rate, high p99 latency, quarantine growing, backup age > 25 hrs, FX rate stale > 36 hrs, period-close failure.

---

## 11. Cutover

Phase 6 acceptance per `docs/plan.md`:

1. ✅ CI green on `main`.
2. ✅ This deploy runbook completed end-to-end.
3. ✅ Backup restored to a fresh DB and ledger reconciles (§9 above).
4. ⬜ Smoketest passes against production-like dataset (run §8 step 4 with the real prior-month dataset; must succeed to cut over).
5. ⬜ One full month of parallel operation (manual books vs. system) with reconciliation report showing < 0.1% variance — this is the *production* sign-off, separate from this deploy.

Once §11.4 is signed off, the system is live.

---

## 12. Future hardening (not required for cutover)

- Postgres streaming replica on a second VPS + repmgr failover.
- Read-only replica for the Reporting Agent + CFO chat.
- Container registry instead of building on the VPS.
- Grafana dashboards committed under `infra/grafana/`.
- Application-layer audit-log replication to an immutable store (S3 Object Lock / Glacier).

---

## Operational quick reference

| Task | Command |
|---|---|
| Restart API | `sudo systemctl restart tuitional-api` |
| Tail logs | `journalctl -fu tuitional-api` |
| Run a backup now | `sudo systemctl start tuitional-backup.service` |
| Restore drill | `/opt/tuitional/scripts/restore.sh` |
| Smoketest | `pytest -m smoketest -q` (under the app venv) |
| Reload nginx | `sudo nginx -t && sudo systemctl reload nginx` |
| Cert renew | `sudo certbot renew --dry-run` |
