# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The trace package for chromite telemetry."""

import contextlib
import os
import sys
from typing import Mapping, Optional


_TRACING_INITIALIZED = False
TRACEPARENT_ENVVAR = "traceparent"


def initialize(enabled: bool = False, log_traces: bool = False):
    """Initialize opentelemetry tracing.

    For most use cases, `telemetry.initialize` should be used since that also
    takes case of any consent and other auxilliary logic related to telemetry.

    Args:
        enabled: Indicates is the traces should be enabled.
        log_traces: Indicates if the traces should be printed to console.
    """

    # The opentelemetry imports are moved inside this function to reduce the
    # package load time. This is especially helpful in scenarios where spans
    # are added to some common library and telemetry is not initialized in all
    # the cases. Nesting these imports would shave off almost 400ms from the
    # import overhead in such cases.
    from chromite.third_party.opentelemetry import context as context_api
    from chromite.third_party.opentelemetry import trace as otel_trace_api
    from chromite.third_party.opentelemetry.sdk import (
        resources as otel_resources,
    )
    from chromite.third_party.opentelemetry.sdk import trace as otel_trace_sdk
    from chromite.third_party.opentelemetry.sdk.trace import (
        export as otel_export,
    )
    from chromite.third_party.opentelemetry.trace.propagation import (
        tracecontext,
    )

    from chromite.utils import hostname_util
    from chromite.utils import telemetry
    from chromite.utils.telemetry import detector
    from chromite.utils.telemetry import exporter
    from chromite.utils.telemetry.trace import otel_trace

    # Need this to globally mark telemetry initialized to enable real imports.
    # pylint: disable=global-statement
    global _TRACING_INITIALIZED
    default_resource = otel_resources.Resource.create(
        {
            otel_resources.SERVICE_NAME: telemetry.SERVICE_NAME,
            "telemetry.version": telemetry.TELEMETRY_VERSION,
        }
    )
    detected_resource = otel_resources.get_aggregated_resources(
        [
            otel_resources.ProcessResourceDetector(),
            otel_resources.OTELResourceDetector(),
            detector.ProcessDetector(),
            detector.SDKSourceDetector(),
            detector.SystemDetector(),
        ]
    )

    resource = detected_resource.merge(default_resource)
    otel_trace_api.set_tracer_provider(
        otel_trace.ChromiteTracerProvider(
            otel_trace_sdk.TracerProvider(resource=resource)
        )
    )

    if log_traces:
        otel_trace_api.get_tracer_provider().add_span_processor(
            otel_export.BatchSpanProcessor(
                otel_export.ConsoleSpanExporter(out=sys.stderr)
            )
        )

    if not hostname_util.is_google_host():
        return

    if enabled:
        otel_trace_api.get_tracer_provider().add_span_processor(
            otel_export.BatchSpanProcessor(exporter.ClearcutSpanExporter())
        )

    if TRACEPARENT_ENVVAR in os.environ:
        ctx = tracecontext.TraceContextTextMapPropagator().extract(os.environ)
        context_api.attach(ctx)

    _TRACING_INITIALIZED = True


def get_tracer(name: str, version: Optional[str] = None) -> "ProxyTracer":
    """Returns a `ProxyTracer` for the module name and version."""
    return ProxyTracer(name, version)


def extract_tracecontext() -> Mapping[str, str]:
    """Extract the current tracecontext into a dict."""
    carrier = {}

    if _TRACING_INITIALIZED:
        from chromite.third_party.opentelemetry.trace.propagation import (
            tracecontext,
        )

        tracecontext.TraceContextTextMapPropagator().inject(carrier)
    return carrier


def get_current_span():
    """Get the currently active span."""

    if _TRACING_INITIALIZED:
        from chromite.third_party.opentelemetry import trace

        return trace.get_current_span()

    return NoOpSpan()


class ProxyTracer:
    """Duck typed equivalent for opentelemetry.trace.Tracer"""

    def __init__(self, name: str, version: Optional[str] = None):
        self._name = name
        self._version = version
        self._inner = None
        self._noop_tracer = NoOpTracer()

    @property
    def _tracer(self):
        if self._inner:
            return self._inner

        if _TRACING_INITIALIZED:
            # Importing here to minimize the overhead for cases
            # where telemetry is not initialized.
            from chromite.third_party.opentelemetry import trace

            self._inner = trace.get_tracer(self._name, self._version)
            return self._inner

        return self._noop_tracer

    @contextlib.contextmanager
    def start_as_current_span(self, *args, **kwargs):
        with self._tracer.start_as_current_span(*args, **kwargs) as span:
            yield span

    def start_span(self, *args, **kwargs):
        return self._tracer.start_span(*args, **kwargs)


class NoOpTracer:
    """Duck typed no-op impl for opentelemetry Tracer."""

    # pylint: disable=unused-argument
    def start_span(self, *args, **kwargs):
        return NoOpSpan()

    @contextlib.contextmanager
    # pylint: disable=unused-argument
    def start_as_current_span(self, *args, **kwargs):
        yield NoOpSpan()


class NoOpSpan:
    """Duck typed no-op impl for opentelemetry Span."""

    # pylint: disable=unused-argument
    def end(self, end_time: Optional[int] = None) -> None:
        pass

    def get_span_context(self):
        return None

    # pylint: disable=unused-argument
    def set_attributes(self, *args, **kwargs) -> None:
        pass

    # pylint: disable=unused-argument
    def set_attribute(self, *args, **kwargs) -> None:
        pass

    # pylint: disable=unused-argument
    def add_event(self, *args, **kwargs) -> None:
        pass

    # pylint: disable=unused-argument
    def update_name(self, name: str) -> None:
        pass

    # pylint: disable=unused-argument
    def is_recording(self) -> bool:
        return False

    # pylint: disable=unused-argument
    def set_status(self, *args, **kwargs) -> None:
        pass

    # pylint: disable=unused-argument
    def record_exception(self, *args, **kwargs) -> None:
        pass

    def __enter__(self) -> "NoOpSpan":
        return self

    # pylint: disable=unused-argument
    def __exit__(self, *args, **kwargs) -> None:
        self.end()
