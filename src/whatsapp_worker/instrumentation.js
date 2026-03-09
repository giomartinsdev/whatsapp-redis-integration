const { NodeSDK } = require('@opentelemetry/sdk-node');
const { OTLPTraceExporter } = require('@opentelemetry/exporter-trace-otlp-http');
const { OTLPMetricExporter } = require('@opentelemetry/exporter-metrics-otlp-http');
const { OTLPLogExporter } = require('@opentelemetry/exporter-logs-otlp-http');
const { getNodeAutoInstrumentations } = require('@opentelemetry/auto-instrumentations-node');
const { SimpleLogRecordProcessor } = require('@opentelemetry/sdk-logs');
const { PeriodicExportingMetricReader } = require('@opentelemetry/sdk-metrics');

process.env.OTEL_SERVICE_NAME = 'whatsapp_node';
if (!process.env.OTEL_RESOURCE_ATTRIBUTES) {
    process.env.OTEL_RESOURCE_ATTRIBUTES = `deployment.environment=${process.env.ENVIRONMENT || 'development'}`;
}

const headers = {};
if (process.env.CLF_SERVICE_TOKEN_CLIENT_ID && process.env.CLF_SERVICE_TOKEN_CLIENT_SECRET) {
    headers['CF-Access-Client-Id'] = process.env.CLF_SERVICE_TOKEN_CLIENT_ID.replace(/^["']|["']$/g, '');
    headers['CF-Access-Client-Secret'] = process.env.CLF_SERVICE_TOKEN_CLIENT_SECRET.replace(/^["']|["']$/g, '');
}

const endpoint = process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://localhost:4318';

const traceExporter = new OTLPTraceExporter({
    url: `${endpoint}/v1/traces`,
    headers: headers,
});

const metricExporter = new OTLPMetricExporter({
    url: `${endpoint}/v1/metrics`,
    headers: headers,
});

const logExporter = new OTLPLogExporter({
    url: `${endpoint}/v1/logs`,
    headers: headers,
});

const sdk = new NodeSDK({
    traceExporter,
    metricReader: new PeriodicExportingMetricReader({
        exporter: metricExporter,
        exportIntervalMillis: 60000,
    }),
    logRecordProcessor: new SimpleLogRecordProcessor(logExporter),
    instrumentations: [getNodeAutoInstrumentations()],
});

sdk.start();

console.log('Telemetry initialized for whatsapp_node');

process.on('SIGTERM', () => {
    sdk.shutdown()
        .then(() => console.log('Tracing terminated'))
        .catch((error) => console.log('Error terminating tracing', error))
        .finally(() => process.exit(0));
});
