# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Defines span exporters to be used with tracer."""

import datetime
import logging
import time
from typing import Callable, Dict, Optional, Sequence
import urllib.request

from chromite.third_party.google.protobuf import json_format
from chromite.third_party.google.protobuf import message as proto_msg
from chromite.third_party.google.protobuf import struct_pb2
from chromite.third_party.opentelemetry import trace as trace_api
from chromite.third_party.opentelemetry.sdk import resources
from chromite.third_party.opentelemetry.sdk import trace
from chromite.third_party.opentelemetry.sdk.trace import export
from chromite.third_party.opentelemetry.util import types

# Required due to incomplete proto support in chromite. This proto usage is not
# tied to the Build API, so delegating the proto handling to api/ does not make
# sense. When proto is better supported in chromite, the protos could, for
# example, live somewhere in utils/ instead.
from chromite.api.gen.chromite.telemetry import clientanalytics_pb2
from chromite.api.gen.chromite.telemetry import trace_span_pb2
from chromite.utils.telemetry import detector
from chromite.utils.telemetry import utils


_DEFAULT_ENDPOINT = "https://play.googleapis.com/log"
_DEFAULT_TIMEOUT = 15
_DEFAULT_FLUSH_TIMEOUT_MILLIS = 30000
_DEAULT_MAX_WAIT_SECS = 60
# Preallocated in Clearcut proto to Build.
_LOG_SOURCE = 2044
# Preallocated in Clearcut proto to Python clients.
_CLIENT_TYPE = 33
_DEFAULT_MAX_QUEUE_SIZE = 1000


class AnonymizingFilter:
    """Applies the anonymizer to TraceSpan messages."""

    def __init__(self, anonymizer: utils.Anonymizer):
        self._anonymizer = anonymizer

    def __call__(
        self, msg: trace_span_pb2.TraceSpan
    ) -> trace_span_pb2.TraceSpan:
        """Applies the anonymizer to TraceSpan message."""
        raw = json_format.MessageToJson(msg)
        json_msg = self._anonymizer.apply(raw)
        output = trace_span_pb2.TraceSpan()
        json_format.Parse(json_msg, output)
        return output


class ClearcutSpanExporter(export.SpanExporter):
    """Exports the spans to google http endpoint."""

    def __init__(
        self,
        endpoint: str = _DEFAULT_ENDPOINT,
        timeout: int = _DEFAULT_TIMEOUT,
        max_wait_secs: int = _DEAULT_MAX_WAIT_SECS,
        max_queue_size: int = _DEFAULT_MAX_QUEUE_SIZE,
        prefilter: Optional[
            Callable[[trace_span_pb2.TraceSpan], trace_span_pb2.TraceSpan]
        ] = None,
    ):
        self._endpoint = endpoint
        self._timeout = timeout
        self._prefilter = prefilter or AnonymizingFilter(utils.Anonymizer())
        self._log_source = _LOG_SOURCE
        self._next_request_dt = datetime.datetime.now()
        self._max_wait_secs = max_wait_secs
        self._queue = []
        self._max_queue_size = max_queue_size

    def export(
        self, spans: Sequence[trace.ReadableSpan]
    ) -> export.SpanExportResult:
        spans = [self._prefilter(self._translate_span(s)) for s in spans]
        self._queue.extend(spans)

        if len(self._queue) >= self._max_queue_size:
            return (
                export.SpanExportResult.SUCCESS
                if self._export_batch()
                else export.SpanExportResult.FAILURE
            )

        return export.SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        self.force_flush()

    def force_flush(
        self, timeout_millis: int = _DEFAULT_FLUSH_TIMEOUT_MILLIS
    ) -> bool:
        if self._queue:
            return self._export_batch(timeout=timeout_millis / 1000)

        return True

    def _translate_context(
        self, data: trace_api.SpanContext
    ) -> trace_span_pb2.TraceSpan.Context:
        ctx = trace_span_pb2.TraceSpan.Context()
        ctx.trace_id = f"0x{trace_api.format_trace_id(data.trace_id)}"
        ctx.span_id = f"0x{trace_api.format_span_id(data.span_id)}"
        ctx.trace_state = repr(data.trace_state)
        return ctx

    def _translate_attributes(
        self, data: types.Attributes
    ) -> struct_pb2.Struct:
        patch = {}
        for k, v in data.items():
            if isinstance(v, tuple):
                v = list(v)
            patch[k] = v

        struct = struct_pb2.Struct()
        try:
            struct.update(patch)
        except Exception as e:
            logging.debug("Set attribute failed: %s", e)
        return struct

    def _translate_span_attributes(
        self, data: trace.ReadableSpan
    ) -> struct_pb2.Struct:
        return self._translate_attributes(data.attributes)

    def _translate_links(
        self, data: trace.ReadableSpan
    ) -> trace_span_pb2.TraceSpan.Link:
        links = []

        for d in data.links:
            link = trace_span_pb2.TraceSpan.Link()
            link.context.MergeFrom(self._translate_context(d.context))
            link.attributes.MergeFrom(self._translate_attributes(d.attributes))
            links.append(link)

        return links

    def _translate_events(
        self, data: trace.ReadableSpan
    ) -> trace_span_pb2.TraceSpan.Event:
        events = []
        for e in data.events:
            event = trace_span_pb2.TraceSpan.Event()
            event.event_time_millis = int(e.timestamp / 1e6)
            event.name = e.name
            event.attributes.MergeFrom(self._translate_attributes(e.attributes))
            events.append(event)
        return events

    def _translate_instrumentation_scope(
        self, data: trace.ReadableSpan
    ) -> trace_span_pb2.TraceSpan.InstrumentationScope:
        s = data.instrumentation_scope
        scope = trace_span_pb2.TraceSpan.InstrumentationScope()
        scope.name = s.name
        scope.version = s.version
        return scope

    def _translate_env(self, data: Dict[str, str]):
        environ = {}
        for k, v in data.items():
            if k.startswith("process.env."):
                key = k.split("process.env.")[1]
                environ[key] = v
        return environ

    def _translate_resource(
        self, data: trace.ReadableSpan
    ) -> trace_span_pb2.TraceSpan.Resource:
        attrs = dict(data.resource.attributes)
        resource = trace_span_pb2.TraceSpan.Resource()
        resource.system.cpu = attrs.pop(detector.CPU_NAME, "")
        resource.system.host_architecture = attrs.pop(
            detector.CPU_ARCHITECTURE, ""
        )
        resource.system.os_name = attrs.pop(detector.OS_NAME, "")
        resource.system.os_version = attrs.pop(resources.OS_DESCRIPTION, "")
        resource.system.os_type = attrs.pop(resources.OS_TYPE, "")
        resource.process.pid = str(attrs.pop(resources.PROCESS_PID, ""))
        resource.process.executable_name = attrs.pop(
            resources.PROCESS_EXECUTABLE_NAME, ""
        )
        resource.process.executable_path = attrs.pop(
            resources.PROCESS_EXECUTABLE_PATH, ""
        )
        resource.process.command = attrs.pop(resources.PROCESS_COMMAND, "")
        resource.process.command_args.extend(
            attrs.pop(resources.PROCESS_COMMAND_ARGS, [])
        )
        resource.process.owner_is_root = (
            attrs.pop(resources.PROCESS_OWNER, 9999) == 0
        )
        resource.process.runtime_name = attrs.pop(
            resources.PROCESS_RUNTIME_NAME, ""
        )
        resource.process.runtime_version = attrs.pop(
            resources.PROCESS_RUNTIME_VERSION, ""
        )
        resource.process.runtime_description = attrs.pop(
            resources.PROCESS_RUNTIME_DESCRIPTION, ""
        )
        resource.process.api_version = str(
            attrs.pop(detector.PROCESS_RUNTIME_API_VERSION, "")
        )
        resource.process.env.update(self._translate_env(attrs))
        resource.attributes.MergeFrom(self._translate_attributes(attrs))
        return resource

    def _translate_status(
        self, data: trace.ReadableSpan
    ) -> trace_span_pb2.TraceSpan.Status:
        status = trace_span_pb2.TraceSpan.Status()

        if data.status.status_code == trace.StatusCode.ERROR:
            status.status_code = (
                trace_span_pb2.TraceSpan.Status.StatusCode.STATUS_CODE_ERROR
            )
        else:
            status.status_code = (
                trace_span_pb2.TraceSpan.Status.StatusCode.STATUS_CODE_OK
            )

        if data.status.description:
            status.message = data.status.description

        return status

    def _translate_sdk(
        self, data: trace.ReadableSpan
    ) -> trace_span_pb2.TraceSpan.TelemetrySdk:
        attrs = data.resource.attributes
        sdk = trace_span_pb2.TraceSpan.TelemetrySdk()
        sdk.name = attrs.get(resources.TELEMETRY_SDK_NAME)
        sdk.version = attrs.get(resources.TELEMETRY_SDK_VERSION)
        sdk.language = attrs.get(resources.TELEMETRY_SDK_LANGUAGE)
        return sdk

    def _translate_kind(
        self, data: trace_api.SpanKind
    ) -> trace_span_pb2.TraceSpan.SpanKind:
        if data == trace_api.SpanKind.INTERNAL:
            return trace_span_pb2.TraceSpan.SpanKind.SPAN_KIND_INTERNAL
        elif data == trace_api.SpanKind.CLIENT:
            return trace_span_pb2.TraceSpan.SpanKind.SPAN_KIND_CLIENT
        elif data == trace_api.SpanKind.SERVER:
            return trace_span_pb2.TraceSpan.SpanKind.SPAN_KIND_SERVER
        return trace_span_pb2.TraceSpan.SpanKind.SPAN_KIND_UNSPECIFIED

    def _translate_span(
        self, data: trace.ReadableSpan
    ) -> trace_span_pb2.TraceSpan:
        span = trace_span_pb2.TraceSpan()
        span.name = data.name
        span.context.MergeFrom(self._translate_context(data.get_span_context()))

        if data.parent is not None:
            if isinstance(data.parent, trace_api.Span):
                ctx = data.parent.context
                span.parent_span_id = (
                    f"0x{trace_api.format_span_id(ctx.span_id)}"
                )
            elif isinstance(data.parent, trace_api.SpanContext):
                span.parent_span_id = (
                    f"0x{trace_api.format_span_id(data.parent.span_id)}"
                )

        span.start_time_millis = int(data.start_time / 1e6)
        span.end_time_millis = int(data.end_time / 1e6)
        span.span_kind = self._translate_kind(data.kind)
        span.instrumentation_scope.MergeFrom(
            self._translate_instrumentation_scope(data)
        )
        span.events.extend(self._translate_events(data))
        span.links.extend(self._translate_links(data))
        span.attributes.MergeFrom(self._translate_span_attributes(data))
        span.status.MergeFrom(self._translate_status(data))
        span.resource.MergeFrom(self._translate_resource(data))
        span.telemetry_sdk.MergeFrom(self._translate_sdk(data))

        return span

    def _export_batch(self, timeout: Optional[int] = None) -> bool:
        """Export the spans to clearcut via http api."""

        spans = self._queue[: self._max_queue_size]
        self._queue = self._queue[self._max_queue_size :]

        while True:
            wait_delta = self._next_request_dt - datetime.datetime.now()
            wait_time = wait_delta.total_seconds()

            # TODO(anujjamwal): Fix this logic.
            # Drop the packets if wait time is more than threshold.
            if wait_time > self._max_wait_secs:
                logging.warning(
                    "dropping %d spans for large wait: %d",
                    len(spans),
                    wait_time,
                )
                return True

            if wait_time > 0:
                time.sleep(wait_time)
                continue

            logrequest = self._prepare_request_body(spans)

            req = urllib.request.Request(
                self._endpoint,
                data=logrequest.SerializeToString(),
                method="POST",
            )
            logresponse = clientanalytics_pb2.LogResponse()

            try:
                with urllib.request.urlopen(
                    req, timeout=timeout or self._timeout
                ) as f:
                    logresponse.ParseFromString(f.read())
            except urllib.error.URLError as e:
                # It is expected that child Pids in build_image which call
                # sys.exit do not have network re-enabled in that namespace, so
                # for now, log this error at the debug level.
                logging.debug(e)
                return False
            except proto_msg.DecodeError as e:
                logging.warning("could not decode data into proto: %s", e)
                return False

            now = datetime.datetime.now()
            delta = datetime.timedelta(
                milliseconds=logresponse.next_request_wait_millis
            )
            self._next_request_dt = now + delta
            return True

    def _prepare_request_body(self, spans) -> clientanalytics_pb2.LogRequest:
        log_request = clientanalytics_pb2.LogRequest()
        log_request.request_time_ms = int(time.time() * 1000)
        log_request.client_info.client_type = _CLIENT_TYPE
        log_request.log_source = self._log_source

        for span in spans:
            log_event = log_request.log_event.add()
            log_event.event_time_ms = int(time.time() * 1000)
            log_event.source_extension = span.SerializeToString()

        return log_request
