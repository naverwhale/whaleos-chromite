# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test the trace implementation."""

import contextlib
from typing import Sequence

from chromite.third_party.opentelemetry import trace as trace_api
from chromite.third_party.opentelemetry.sdk import trace as trace_sdk
from chromite.third_party.opentelemetry.sdk.trace import export as export_sdk

from chromite.utils.telemetry.trace import otel_trace


class SpanExporterStub(export_sdk.SpanExporter):
    """Stub for SpanExporter."""

    def __init__(self):
        self._spans = []

    @property
    def spans(self):
        return self._spans

    def export(
        self, spans: Sequence[trace_sdk.ReadableSpan]
    ) -> export_sdk.SpanExportResult:
        self._spans.extend(spans)

        return export_sdk.SpanExportResult.SUCCESS


class ExceptionWithFailedPackages(Exception):
    """Exception with failed_packages."""

    def __init__(self, msg: str, pkgs: Sequence[str]) -> None:
        super().__init__(msg)

        self.failed_packages = pkgs


def test_chromite_span_to_capture_keyboard_interrupt_as_decorator():
    """Test chromite span can capture KeyboardInterrupt as decorator."""
    exporter = SpanExporterStub()
    provider = otel_trace.ChromiteTracerProvider(trace_sdk.TracerProvider())
    provider.add_span_processor(
        export_sdk.BatchSpanProcessor(span_exporter=exporter)
    )
    tracer = provider.get_tracer(__name__)

    @tracer.start_as_current_span("test-span")
    def test_function():
        raise KeyboardInterrupt()

    with contextlib.suppress(KeyboardInterrupt):
        test_function()

    provider.shutdown()

    assert len(exporter.spans) == 1
    assert exporter.spans[0].events[0].name == "exception"
    assert (
        exporter.spans[0].events[0].attributes["exception.type"]
        == "KeyboardInterrupt"
    )
    assert exporter.spans[0].status.status_code == trace_api.StatusCode.OK


def test_chromite_span_to_capture_keyboard_interrupt_in_context():
    """Test chromite span can capture KeyboardInterrupt in context."""
    exporter = SpanExporterStub()
    provider = otel_trace.ChromiteTracerProvider(trace_sdk.TracerProvider())
    provider.add_span_processor(
        export_sdk.BatchSpanProcessor(span_exporter=exporter)
    )
    tracer = provider.get_tracer(__name__)

    with contextlib.suppress(KeyboardInterrupt):
        with tracer.start_as_current_span("test-span"):
            raise KeyboardInterrupt()

    provider.shutdown()

    assert len(exporter.spans) == 1
    assert exporter.spans[0].events[0].name == "exception"
    assert (
        exporter.spans[0].events[0].attributes["exception.type"]
        == "KeyboardInterrupt"
    )
    assert exporter.spans[0].status.status_code == trace_api.StatusCode.OK


def test_chromite_span_to_capture_failed_packages_in_context():
    """Test chromite span can capture failed_packages in context."""
    exporter = SpanExporterStub()
    provider = otel_trace.ChromiteTracerProvider(trace_sdk.TracerProvider())
    provider.add_span_processor(
        export_sdk.BatchSpanProcessor(span_exporter=exporter)
    )
    tracer = provider.get_tracer(__name__)

    with contextlib.suppress(ExceptionWithFailedPackages):
        with tracer.start_as_current_span("test-span"):
            raise ExceptionWithFailedPackages(
                msg="testing", pkgs=["dev-python/boto"]
            )

    provider.shutdown()

    assert len(exporter.spans) == 1
    assert exporter.spans[0].status.status_code == trace_api.StatusCode.ERROR
    assert (
        exporter.spans[0].status.description
        == "ExceptionWithFailedPackages: testing"
    )
    assert list(exporter.spans[0].events[0].attributes["failed_packages"]) == [
        "dev-python/boto"
    ]
    assert (
        exporter.spans[0].events[0].attributes["exception.type"]
        == "ExceptionWithFailedPackages"
    )


def test_chromite_span_to_capture_failed_packages_as_decorator():
    """Test chromite span can capture failed_packages as decorator."""
    exporter = SpanExporterStub()
    provider = otel_trace.ChromiteTracerProvider(trace_sdk.TracerProvider())
    provider.add_span_processor(
        export_sdk.BatchSpanProcessor(span_exporter=exporter)
    )
    tracer = provider.get_tracer(__name__)

    @tracer.start_as_current_span("test-span")
    def test_function():
        raise ExceptionWithFailedPackages(
            msg="testing", pkgs=["dev-python/boto"]
        )

    with contextlib.suppress(ExceptionWithFailedPackages):
        test_function()

    provider.shutdown()

    assert len(exporter.spans) == 1
    assert exporter.spans[0].status.status_code == trace_api.StatusCode.ERROR
    assert (
        exporter.spans[0].status.description
        == "ExceptionWithFailedPackages: testing"
    )
    assert list(exporter.spans[0].events[0].attributes["failed_packages"]) == [
        "dev-python/boto"
    ]
    assert (
        exporter.spans[0].events[0].attributes["exception.type"]
        == "ExceptionWithFailedPackages"
    )
