"""
Tests for src.middleware: RequestIDMiddleware response headers and the
CCARequestIdSpanProcessor that broadcasts the per-request UUID onto every
OTel span as `forgg.cca_request_id`.

Covers the CCA-side of the ACA↔CCA attribute-correlation contract
(MSG-ACA-20260430-001 / MSG-CCA-20260501-002).
"""

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from src.middleware import (
    CCARequestIdSpanProcessor,
    RequestIDMiddleware,
    cca_request_id_ctx,
)


# ---------------------------------------------------------------------------
# RequestIDMiddleware: response headers
# ---------------------------------------------------------------------------


def _make_test_app() -> FastAPI:
    """Build a minimal FastAPI app with only RequestIDMiddleware mounted."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return app


def test_request_id_middleware_emits_both_headers():
    """Every response carries X-Request-Id AND X-Forgg-CCA-Request-Id with the
    same value (single mint, two header aliases)."""
    client = TestClient(_make_test_app())

    response = client.get("/ping")

    assert response.status_code == 200
    assert "x-request-id" in response.headers
    assert "x-forgg-cca-request-id" in response.headers
    assert (
        response.headers["x-request-id"]
        == response.headers["x-forgg-cca-request-id"]
    )


def test_request_id_middleware_honors_inbound_x_request_id():
    """If a client sends X-Request-Id, the middleware reuses it for both
    headers rather than minting a new one."""
    client = TestClient(_make_test_app())
    sentinel = "client-supplied-id-123"

    response = client.get("/ping", headers={"X-Request-Id": sentinel})

    assert response.headers["x-request-id"] == sentinel
    assert response.headers["x-forgg-cca-request-id"] == sentinel


def test_request_id_middleware_mints_uuid_when_missing():
    """When no inbound X-Request-Id is present, a UUID is minted."""
    client = TestClient(_make_test_app())

    response = client.get("/ping")
    minted = response.headers["x-request-id"]

    # uuid4() string form: 8-4-4-4-12 hex with dashes
    assert len(minted) == 36
    assert minted.count("-") == 4


# ---------------------------------------------------------------------------
# CCARequestIdSpanProcessor: span attribute broadcast
# ---------------------------------------------------------------------------


def test_span_processor_sets_attribute_when_contextvar_is_set():
    """When the contextvar is populated, on_start sets the span attribute."""
    processor = CCARequestIdSpanProcessor()
    span = MagicMock()
    span.is_recording.return_value = True

    token = cca_request_id_ctx.set("abc-123")
    try:
        processor.on_start(span)
    finally:
        cca_request_id_ctx.reset(token)

    span.set_attribute.assert_called_once_with("forgg.cca_request_id", "abc-123")


def test_span_processor_noop_when_contextvar_unset():
    """When the contextvar is not set, on_start does nothing."""
    processor = CCARequestIdSpanProcessor()
    span = MagicMock()
    span.is_recording.return_value = True

    # Don't set the contextvar — default is None.
    processor.on_start(span)

    span.set_attribute.assert_not_called()


def test_span_processor_noop_when_span_not_recording():
    """When a span is not recording, on_start skips the attribute set."""
    processor = CCARequestIdSpanProcessor()
    span = MagicMock()
    span.is_recording.return_value = False

    token = cca_request_id_ctx.set("abc-123")
    try:
        processor.on_start(span)
    finally:
        cca_request_id_ctx.reset(token)

    span.set_attribute.assert_not_called()


def test_span_processor_lifecycle_methods_no_raise():
    """on_end / shutdown / force_flush are no-ops; they should not raise."""
    processor = CCARequestIdSpanProcessor()

    processor.on_end(MagicMock())  # no-op
    processor.shutdown()  # no-op
    assert processor.force_flush() is True


# ---------------------------------------------------------------------------
# Integration: SpanProcessor + real OTel tracer + RequestIDMiddleware
# ---------------------------------------------------------------------------


def test_span_processor_with_real_tracer_records_attribute():
    """End-to-end: register the processor on a real TracerProvider, set the
    contextvar, start a span, and verify the exported span carries
    `forgg.cca_request_id` with the right value."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    provider.add_span_processor(CCARequestIdSpanProcessor())

    tracer = provider.get_tracer("test")

    token = cca_request_id_ctx.set("integration-test-id-789")
    try:
        with tracer.start_as_current_span("test-span"):
            pass
    finally:
        cca_request_id_ctx.reset(token)

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].attributes.get("forgg.cca_request_id") == "integration-test-id-789"
