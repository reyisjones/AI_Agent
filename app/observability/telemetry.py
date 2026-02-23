"""
OpenTelemetry bootstrap — call setup_telemetry() once at application startup.

Traces and logs are exported via OTLP when OTLP_ENDPOINT is configured.
If the endpoint is empty, a simple console exporter is used (dev mode).
"""
from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.config import get_settings

# Context variable so every log line in a request carries a trace id
_request_id_var: ContextVar[str] = ContextVar("request_id", default="")

_in_memory_exporter: Optional[InMemorySpanExporter] = None  # exposed for tests


def setup_telemetry() -> TracerProvider:
    settings = get_settings()
    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": settings.service_version,
            "deployment.environment": settings.app_env,
        }
    )
    provider = TracerProvider(resource=resource)

    if settings.otlp_endpoint:
        # Lazy import so the package is only required when actually used
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore[import]
            OTLPSpanExporter,
        )

        exporter = OTLPSpanExporter(endpoint=settings.otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    else:
        # Development — also keep spans in memory for integration tests
        global _in_memory_exporter
        _in_memory_exporter = InMemorySpanExporter()
        provider.add_span_processor(BatchSpanProcessor(_in_memory_exporter))
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _configure_logging(settings.log_level)
    return provider


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format=(
            "%(asctime)s %(levelname)-8s %(name)s "
            "[trace_id=%(trace_id)s request_id=%(request_id)s] %(message)s"
        ),
    )
    # Inject trace/request ids into every LogRecord
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):  # type: ignore[no-untyped-def]
        record = old_factory(*args, **kwargs)
        span = trace.get_current_span()
        ctx = span.get_span_context()
        record.trace_id = format(ctx.trace_id, "032x") if ctx.is_valid else "0" * 32
        record.request_id = _request_id_var.get()
        return record

    logging.setLogRecordFactory(record_factory)


def get_tracer(name: str = "ai-agent") -> trace.Tracer:
    return trace.get_tracer(name)


def new_request_id() -> str:
    rid = uuid.uuid4().hex
    _request_id_var.set(rid)
    return rid


def get_request_id() -> str:
    return _request_id_var.get() or uuid.uuid4().hex


def get_in_memory_exporter() -> Optional[InMemorySpanExporter]:
    return _in_memory_exporter
