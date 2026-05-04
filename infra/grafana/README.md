# Grafana dashboards

These JSON files are Grafana dashboard models (schema v39, Grafana 10+).
Import them via **Dashboards → Import → Upload JSON file** or copy them
into a provisioned `dashboards/` directory.

| File | What it shows |
|---|---|
| `tuitional-overview.json` | HTTP request rate, p50/p99 latency, error rate, in-flight |
| `tuitional-ledger.json` | Journals posted/rejected, quarantine open, recent journal volume |

Both reference a Prometheus datasource named `Prometheus` — change the
`datasource.uid` field if yours differs. Metric names are emitted by
`src/api/observability.py`; alert rules live in
`infra/prometheus/alerts.yml`.
