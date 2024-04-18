# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Chromite specific implementation of the otel trace api."""

import contextlib
import types as python_types
from typing import Any, Dict, Iterator, Optional, Sequence, Union

from chromite.third_party.opentelemetry import context as otel_context_api
from chromite.third_party.opentelemetry import trace as otel_trace_api
from chromite.third_party.opentelemetry.sdk import trace as otel_trace_sdk
from chromite.third_party.opentelemetry.util import types as otel_types


class ChromiteSpan(otel_trace_api.Span):
    """Chromite specific otel span implementation."""

    def __init__(self, inner: otel_trace_sdk.Span):
        self._inner = inner

    def end(self, end_time: Optional[int] = None) -> None:
        self._inner.end(end_time=end_time)

    def get_span_context(self) -> otel_trace_api.SpanContext:
        return self._inner.get_span_context()

    def set_attributes(
        self, attributes: Dict[str, otel_types.AttributeValue]
    ) -> None:
        self._inner.set_attributes(attributes)

    def set_attribute(self, key: str, value: otel_types.AttributeValue) -> None:
        self._inner.set_attribute(key, value)

    def add_event(
        self,
        name: str,
        attributes: otel_types.Attributes = None,
        timestamp: Optional[int] = None,
    ) -> None:
        self._inner.add_event(name, attributes=attributes, timestamp=timestamp)

    def update_name(self, name: str) -> None:
        self._inner.update_name(name)

    def is_recording(self) -> bool:
        return self._inner.is_recording()

    def set_status(
        self,
        status: Union[otel_trace_api.Status, otel_trace_api.StatusCode],
        description: Optional[str] = None,
    ) -> None:
        self._inner.set_status(status, description)

    def record_exception(
        self,
        exception: Exception,
        attributes: otel_types.Attributes = None,
        timestamp: Optional[int] = None,
        escaped: bool = False,
    ) -> None:
        # Create a mutable dict from the passed attributes or create a new dict
        # if empty or null. This ensures that the passed dict is not mutated.
        attributes = dict(attributes or {})
        if hasattr(exception, "failed_packages") and isinstance(
            exception.failed_packages, list
        ):
            attributes["failed_packages"] = [
                str(f) for f in exception.failed_packages
            ]

        self._inner.record_exception(
            exception,
            attributes=attributes,
            timestamp=timestamp,
            escaped=escaped,
        )

    def __enter__(self) -> "ChromiteSpan":
        return self

    def __exit__(
        self,
        exc_type: Optional[BaseException],
        exc_val: Optional[BaseException],
        exc_tb: Optional[python_types.TracebackType],
    ) -> None:
        if exc_val and self.is_recording():
            if self._inner._record_exception:
                self.record_exception(exception=exc_val, escaped=True)

            if self._inner._set_status_on_exception:
                self.set_status(
                    otel_trace_api.Status(
                        status_code=otel_trace_api.StatusCode.ERROR,
                        description=f"{exc_type.__name__}: {exc_val}",
                    )
                )

        super().__exit__(exc_type, exc_val, exc_tb)

    def __getattr__(self, name: str) -> Any:
        """Method allows to delegate method calls."""
        return getattr(self._inner, name)


@contextlib.contextmanager
def use_span(
    span: otel_trace_api.Span,
    end_on_exit: bool = False,
    record_exception: bool = True,
    set_status_on_exception: bool = True,
) -> Iterator[otel_trace_api.Span]:
    """Takes a non-active span and activates it in the current context."""

    try:
        token = otel_context_api.attach(
            # pylint: disable=protected-access
            # This is needed since the key needs to be the same as
            # used in the rest of opentelemetry code.
            otel_context_api.set_value(otel_trace_api._SPAN_KEY, span)
        )
        try:
            yield span
        finally:
            otel_context_api.detach(token)

    except KeyboardInterrupt as exc:
        if span.is_recording():
            if record_exception:
                span.record_exception(exc)

            if set_status_on_exception:
                span.set_status(otel_trace_api.StatusCode.OK)
        raise
    except BaseException as exc:  # pylint: disable=broad-except
        if span.is_recording():
            # Record the exception as an event
            if record_exception:
                span.record_exception(exc)

            # Set status in case exception was raised
            if set_status_on_exception:
                span.set_status(
                    otel_trace_api.Status(
                        status_code=otel_trace_api.StatusCode.ERROR,
                        description=f"{type(exc).__name__}: {exc}",
                    )
                )
        raise

    finally:
        if end_on_exit:
            span.end()


class ChromiteTracer(otel_trace_api.Tracer):
    """Chromite specific otel tracer."""

    def __init__(self, inner: otel_trace_sdk.Tracer):
        self._inner = inner

    def start_span(
        self,
        name: str,
        context: Optional[otel_context_api.Context] = None,
        kind: otel_trace_api.SpanKind = otel_trace_api.SpanKind.INTERNAL,
        attributes: otel_types.Attributes = None,
        links: Optional[Sequence[otel_trace_api.Link]] = None,
        start_time: Optional[int] = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True,
    ) -> otel_trace_api.Span:
        span = self._inner.start_span(
            name,
            context=context,
            kind=kind,
            attributes=attributes,
            links=links,
            start_time=start_time,
            record_exception=record_exception,
            set_status_on_exception=set_status_on_exception,
        )
        return ChromiteSpan(span)

    @contextlib.contextmanager
    def start_as_current_span(
        self,
        name: str,
        context: Optional[otel_context_api.Context] = None,
        kind: otel_trace_api.SpanKind = otel_trace_api.SpanKind.INTERNAL,
        attributes: otel_types.Attributes = None,
        links: Optional[Sequence[otel_trace_api.Link]] = None,
        start_time: Optional[int] = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True,
        end_on_exit: bool = True,
    ) -> Iterator[otel_trace_api.Span]:
        span = self.start_span(
            name=name,
            context=context,
            kind=kind,
            attributes=attributes,
            links=links,
            start_time=start_time,
            record_exception=record_exception,
            set_status_on_exception=set_status_on_exception,
        )
        with use_span(
            span,
            end_on_exit=end_on_exit,
            record_exception=record_exception,
            set_status_on_exception=set_status_on_exception,
        ) as span_context:
            yield span_context


class ChromiteTracerProvider(otel_trace_api.TracerProvider):
    """Chromite specific otel tracer provider."""

    def __init__(self, inner: otel_trace_sdk.TracerProvider):
        self._inner = inner

    def get_tracer(
        self,
        instrumenting_module_name: str,
        instrumenting_library_version: Optional[str] = None,
        schema_url: Optional[str] = None,
    ) -> otel_trace_api.Tracer:
        tracer = self._inner.get_tracer(
            instrumenting_module_name=instrumenting_module_name,
            instrumenting_library_version=instrumenting_library_version,
            schema_url=schema_url,
        )
        return ChromiteTracer(tracer)

    def __getattr__(self, name: str) -> Any:
        """Method allows to delegate method calls."""
        return getattr(self._inner, name)
