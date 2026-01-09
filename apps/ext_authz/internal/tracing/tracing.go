// Package tracing provides OpenTelemetry distributed tracing configuration.
//
// Architecture (CNCF Best Practices):
//
//	App (OTel SDK) → OTLP/gRPC (4317) → Jaeger Collector → Elasticsearch
//
// References:
//   - Google Dapper: Low overhead, application-level transparency
//   - Netflix Edgar: Request interceptor pattern, async collection
//   - Uber Jaeger: OpenTelemetry native, adaptive sampling
package tracing

import (
	"context"
	"os"
	"strconv"
	"time"

	"go.opentelemetry.io/contrib/propagators/b3"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
	"go.opentelemetry.io/otel/trace"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	"github.com/eco2-team/backend/domains/ext-authz/internal/constants"
)

// Default configuration
const (
	defaultEndpoint     = "jaeger-collector-clusterip.istio-system.svc.cluster.local:4317"
	defaultSamplingRate = 1.0
	defaultTimeout      = 5 * time.Second
)

// Environment variable names
const (
	envEndpoint     = "OTEL_EXPORTER_OTLP_ENDPOINT"
	envSamplingRate = "OTEL_SAMPLING_RATE"
	envEnabled      = "OTEL_ENABLED"
)

// Config holds tracing configuration.
type Config struct {
	ServiceName    string
	ServiceVersion string
	Environment    string
	Endpoint       string
	SamplingRate   float64
	Enabled        bool
}

// DefaultConfig returns default tracing configuration from environment.
func DefaultConfig() *Config {
	enabled := true
	if v := os.Getenv(envEnabled); v != "" {
		enabled = v == "true"
	}

	samplingRate := defaultSamplingRate
	if v := os.Getenv(envSamplingRate); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			samplingRate = f
		}
	}

	endpoint := os.Getenv(envEndpoint)
	if endpoint == "" {
		endpoint = defaultEndpoint
	}

	return &Config{
		ServiceName:    constants.ServiceName,
		ServiceVersion: constants.ServiceVersion,
		Environment:    os.Getenv(constants.EnvEnvironment),
		Endpoint:       endpoint,
		SamplingRate:   samplingRate,
		Enabled:        enabled,
	}
}

// TracerProvider wraps the OpenTelemetry TracerProvider.
type TracerProvider struct {
	provider *sdktrace.TracerProvider
}

// Init initializes OpenTelemetry tracing.
func Init(ctx context.Context, cfg *Config) (*TracerProvider, error) {
	if cfg == nil {
		cfg = DefaultConfig()
	}

	if !cfg.Enabled {
		return nil, nil
	}

	// Create OTLP gRPC exporter
	conn, err := grpc.NewClient(
		cfg.Endpoint,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		return nil, err
	}

	exporter, err := otlptracegrpc.New(ctx, otlptracegrpc.WithGRPCConn(conn))
	if err != nil {
		return nil, err
	}

	// Create resource with service metadata
	// Use resource.New instead of resource.Merge to avoid schema URL conflicts
	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceName(cfg.ServiceName),
			semconv.ServiceVersion(cfg.ServiceVersion),
			attribute.String("deployment.environment", cfg.Environment),
			attribute.String("telemetry.sdk.name", "opentelemetry"),
			attribute.String("telemetry.sdk.language", "go"),
		),
		resource.WithHost(),
		resource.WithProcess(),
	)
	if err != nil {
		return nil, err
	}

	// Create sampler (ratio-based for production)
	sampler := sdktrace.TraceIDRatioBased(cfg.SamplingRate)

	// Create TracerProvider
	tp := sdktrace.NewTracerProvider(
		sdktrace.WithResource(res),
		sdktrace.WithSampler(sampler),
		sdktrace.WithBatcher(exporter,
			sdktrace.WithMaxQueueSize(2048),
			sdktrace.WithMaxExportBatchSize(512),
			sdktrace.WithBatchTimeout(time.Second),
		),
	)

	// Set global TracerProvider and propagator
	// B3 propagator for Istio/Envoy compatibility
	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
		b3.New(b3.WithInjectEncoding(b3.B3MultipleHeader)),
	))

	return &TracerProvider{provider: tp}, nil
}

// Shutdown gracefully shuts down the tracer provider.
func (tp *TracerProvider) Shutdown(ctx context.Context) error {
	if tp == nil || tp.provider == nil {
		return nil
	}

	ctx, cancel := context.WithTimeout(ctx, defaultTimeout)
	defer cancel()

	return tp.provider.Shutdown(ctx)
}

// Tracer returns a tracer for the given name.
func Tracer(name string) trace.Tracer {
	return otel.Tracer(name)
}

// StartSpan starts a new span with the given name and attributes.
func StartSpan(ctx context.Context, name string, attrs ...attribute.KeyValue) (context.Context, trace.Span) {
	return Tracer("ext-authz").Start(ctx, name, trace.WithAttributes(attrs...))
}

// SpanFromContext returns the current span from context.
func SpanFromContext(ctx context.Context) trace.Span {
	return trace.SpanFromContext(ctx)
}

// AddEvent adds an event to the current span.
func AddEvent(ctx context.Context, name string, attrs ...attribute.KeyValue) {
	span := trace.SpanFromContext(ctx)
	span.AddEvent(name, trace.WithAttributes(attrs...))
}

// SetError marks the span as an error.
func SetError(ctx context.Context, err error, description string) {
	span := trace.SpanFromContext(ctx)
	span.RecordError(err)
	span.SetStatus(codes.Error, description)
}

// RecordError records an error on the current span.
func RecordError(ctx context.Context, err error) {
	span := trace.SpanFromContext(ctx)
	span.RecordError(err)
}
