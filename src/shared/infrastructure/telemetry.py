from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.trace import StatusCode

from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry._logs import set_logger_provider

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.metrics import set_meter_provider

_logger = logging.getLogger(__name__)

_DEFAULT_HEARTBEAT_INTERVAL = 60


def _heartbeat_loop(service_name: str, interval_seconds: int) -> None:
    _tracer = trace.get_tracer(service_name)
    while True:
        time.sleep(interval_seconds)
        try:
            with _tracer.start_as_current_span(
                "heartbeat",
                attributes={
                    "service.name": service_name,
                    "heartbeat": True,
                },
            ) as span:
                span.set_status(StatusCode.OK)
        except Exception:
            pass


def setup_telemetry(
    service_name: str,
    service_version: str = "1.0.0",
) -> Optional[trace.Tracer]:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip().strip('"').strip("'")
    if not endpoint:
        _logger.warning("OTEL_EXPORTER_OTLP_ENDPOINT not set — telemetry disabled")
        return None

    client_id = os.getenv("CLF_SERVICE_TOKEN_CLIENT_ID", "").strip().strip('"').strip("'")
    client_secret = os.getenv("CLF_SERVICE_TOKEN_CLIENT_SECRET", "").strip().strip('"').strip("'")
    environment = os.getenv("ENVIRONMENT", "development").strip()
    heartbeat_interval = int(os.getenv("OTEL_HEARTBEAT_INTERVAL_SECONDS", str(_DEFAULT_HEARTBEAT_INTERVAL)))

    _logger.info(f"🔭 Configuring telemetry for '{service_name}'...")
    _logger.info(f"   OTEL endpoint: {endpoint}")
    _logger.info(f"   CF-Access-Client-Id present: {bool(client_id)}")
    _logger.info(f"   CF-Access-Client-Secret present: {bool(client_secret)}")
    _logger.info(f"   Heartbeat interval: {heartbeat_interval}s")

    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
        "deployment.environment": environment,
    })

    headers = {}
    if client_id and client_secret:
        headers["CF-Access-Client-Id"] = client_id
        headers["CF-Access-Client-Secret"] = client_secret

    traces_endpoint = f"{endpoint.rstrip('/')}/v1/traces"

    try:
        trace_exporter = OTLPSpanExporter(
            endpoint=traces_endpoint,
            headers=headers,
            timeout=10,
        )
    except Exception as e:
        _logger.error(f"❌ Failed to create OTLP trace exporter: {e}")
        return None

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(
        trace_exporter,
        max_queue_size=512,
        max_export_batch_size=64,
        schedule_delay_millis=5000,
    ))
    trace.set_tracer_provider(provider)
    _logger.info(f"✅ Traces enabled → {traces_endpoint}")

    logs_endpoint = f"{endpoint.rstrip('/')}/v1/logs"

    try:
        log_exporter = OTLPLogExporter(
            endpoint=logs_endpoint,
            headers=headers,
            timeout=10,
        )

        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(log_exporter)
        )
        set_logger_provider(logger_provider)

        otel_handler = LoggingHandler(
            level=logging.INFO,
            logger_provider=logger_provider,
        )
        logging.getLogger().addHandler(otel_handler)

        global _otel_log_handler
        _otel_log_handler = otel_handler

        _logger.info(f"✅ Logs enabled → {logs_endpoint}")
    except Exception as e:
        _logger.error(f"❌ Failed to configure log export: {e}")

    metrics_endpoint = f"{endpoint.rstrip('/')}/v1/metrics"

    try:
        metric_exporter = OTLPMetricExporter(
            endpoint=metrics_endpoint,
            headers=headers,
            timeout=10,
        )

        metric_reader = PeriodicExportingMetricReader(
            metric_exporter,
            export_interval_millis=60000,  # export every 60s
        )

        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[metric_reader],
        )
        set_meter_provider(meter_provider)

        _logger.info(f"✅ Metrics enabled → {metrics_endpoint}")

        try:
            from opentelemetry.instrumentation.system_metrics import (
                SystemMetricsInstrumentor,
            )
            SystemMetricsInstrumentor().instrument()
            _logger.info("✅ System metrics instrumentor started")
        except ImportError:
            _logger.warning(
                "⚠️  opentelemetry-instrumentation-system-metrics not installed — "
                "system metrics disabled"
            )
        except Exception as e:
            _logger.error(f"❌ Failed to start system metrics: {e}")

    except Exception as e:
        _logger.error(f"❌ Failed to configure metrics export: {e}")

    try:
        test_tracer = trace.get_tracer(service_name, service_version)
        with test_tracer.start_as_current_span(
            "telemetry.startup_check",
            attributes={
                "service.name": service_name,
                "telemetry.test": True,
            },
        ) as span:
            span.set_status(StatusCode.OK)
        _logger.info(f"📡 Startup check span created for '{service_name}'")
    except Exception as e:
        _logger.error(f"❌ Failed to create startup check span: {e}")

    if heartbeat_interval > 0:
        t = threading.Thread(
            target=_heartbeat_loop,
            args=(service_name, heartbeat_interval),
            daemon=True,
            name=f"otel-heartbeat-{service_name}",
        )
        t.start()
        _logger.info(f"💓 Heartbeat thread started (every {heartbeat_interval}s)")

    return trace.get_tracer(service_name, service_version)


_otel_log_handler: Optional[logging.Handler] = None


def attach_otel_to_loggers(*logger_names: str) -> None:
    if _otel_log_handler is None:
        return
    for name in logger_names:
        lg = logging.getLogger(name)
        if _otel_log_handler not in lg.handlers:
            lg.addHandler(_otel_log_handler)
            _logger.debug(f"Attached OTEL handler to logger '{name}'")


def get_tracer(name: str = __name__) -> trace.Tracer:
    return trace.get_tracer(name)
