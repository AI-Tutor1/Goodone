"""Observability middleware + Prometheus metrics.

Three concerns:

* **Request IDs.** Every incoming request is tagged with an ID (or echoes
  one from ``X-Request-ID`` if present). The ID is bound into the
  structlog contextvar so every log line within the request carries it,
  and is echoed back on the response.
* **Structured access log.** One log line per request with method, path,
  status, duration_ms, request_id.
* **Prometheus metrics.** Plain-text exposition at ``/metrics``. Counters
  for total requests, in-flight gauges, latency histogram, and a small
  business-counter for posted journals.

Metrics are intentionally minimal — the alert rules in
``infra/prometheus/alerts.yml`` only fire on the ones we expose here.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import ClassVar

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger("api.observability")


# ---------------------------------------------------------------------------
# Prometheus metrics (plain stdlib — avoids the prometheus_client dep)
# ---------------------------------------------------------------------------


class _Counter:
    def __init__(self, name: str, help_text: str) -> None:
        self.name = name
        self.help_text = help_text
        self._labels: dict[tuple[str, ...], float] = {}

    def inc(self, labels: tuple[str, ...] = (), amount: float = 1.0) -> None:
        self._labels[labels] = self._labels.get(labels, 0.0) + amount

    def render(self, label_keys: tuple[str, ...] = ()) -> str:
        out = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} counter"]
        if not self._labels:
            out.append(f"{self.name}_total 0")
            return "\n".join(out)
        for label_values, count in sorted(self._labels.items()):
            if label_keys:
                label_str = ",".join(
                    f'{k}="{v}"' for k, v in zip(label_keys, label_values, strict=True)
                )
                out.append(f"{self.name}_total{{{label_str}}} {count}")
            else:
                out.append(f"{self.name}_total {count}")
        return "\n".join(out)


class _Gauge:
    def __init__(self, name: str, help_text: str) -> None:
        self.name = name
        self.help_text = help_text
        self._value = 0.0

    def inc(self, amount: float = 1.0) -> None:
        self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        self._value -= amount

    def set(self, value: float) -> None:
        self._value = value

    def render(self) -> str:
        return (
            f"# HELP {self.name} {self.help_text}\n"
            f"# TYPE {self.name} gauge\n"
            f"{self.name} {self._value}"
        )


class _Histogram:
    """Naive histogram — we only need a few buckets."""

    BUCKETS_S: ClassVar[list[float]] = [
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
    ]

    def __init__(self, name: str, help_text: str) -> None:
        self.name = name
        self.help_text = help_text
        self._counts = [0] * (len(self.BUCKETS_S) + 1)  # last is +Inf
        self._sum = 0.0
        self._n = 0

    def observe(self, seconds: float) -> None:
        for i, bound in enumerate(self.BUCKETS_S):
            if seconds <= bound:
                self._counts[i] += 1
                break
        else:
            self._counts[-1] += 1
        # cumulative counts are computed at render time
        self._sum += seconds
        self._n += 1

    def render(self) -> str:
        out = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} histogram"]
        cum = 0
        for i, bound in enumerate(self.BUCKETS_S):
            cum += self._counts[i]
            out.append(f'{self.name}_bucket{{le="{bound}"}} {cum}')
        cum += self._counts[-1]
        out.append(f'{self.name}_bucket{{le="+Inf"}} {cum}')
        out.append(f"{self.name}_sum {self._sum}")
        out.append(f"{self.name}_count {self._n}")
        return "\n".join(out)


# Public registry — agents and routes import these by name.
http_requests_total = _Counter(
    "tuitional_http_requests",
    "Total HTTP requests handled by the FastAPI app.",
)
http_in_flight = _Gauge(
    "tuitional_http_in_flight",
    "In-flight HTTP requests right now.",
)
http_request_duration_seconds = _Histogram(
    "tuitional_http_request_duration_seconds",
    "Request duration in seconds.",
)
journals_posted_total = _Counter(
    "tuitional_journals_posted",
    "Total journal entries successfully posted.",
)
journals_rejected_total = _Counter(
    "tuitional_journals_rejected",
    "Total journal-entry post attempts rejected (sums all error types).",
)
quarantine_open_gauge = _Gauge(
    "tuitional_quarantine_open",
    "Open rows in staging.data_quality_quarantine.",
)


def render_prometheus() -> str:
    """Render every registered metric in Prometheus text format."""
    return (
        "\n\n".join(
            [
                http_requests_total.render(("method", "path", "status")),
                http_in_flight.render(),
                http_request_duration_seconds.render(),
                journals_posted_total.render(("source_kind",)),
                journals_rejected_total.render(("source_kind", "error")),
                quarantine_open_gauge.render(),
            ],
        )
        + "\n"
    )


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Tag every request with an ID, log it, and track Prometheus metrics."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        structlog.contextvars.bind_contextvars(request_id=rid)

        http_in_flight.inc()
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            http_requests_total.inc(("internal", request.url.path, "500"))
            http_in_flight.dec()
            duration = time.perf_counter() - start
            http_request_duration_seconds.observe(duration)
            logger.error(
                "http_request_error",
                method=request.method,
                path=request.url.path,
                duration_ms=round(duration * 1000, 2),
            )
            structlog.contextvars.unbind_contextvars("request_id")
            raise

        duration = time.perf_counter() - start
        http_request_duration_seconds.observe(duration)
        http_in_flight.dec()
        http_requests_total.inc((request.method, request.url.path, str(response.status_code)))

        response.headers["X-Request-ID"] = rid
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration * 1000, 2),
        )
        structlog.contextvars.unbind_contextvars("request_id")
        return response
