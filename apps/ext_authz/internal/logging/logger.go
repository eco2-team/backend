// Package logging provides ECS-compatible structured logging for ext-authz.
package logging

import (
	"context"
	"io"
	"log/slog"
	"os"
	"time"

	"github.com/eco2-team/backend/domains/ext-authz/internal/constants"
)

const (
	// Log levels (re-exported for convenience)
	LevelDebug = slog.LevelDebug
	LevelInfo  = slog.LevelInfo
	LevelWarn  = slog.LevelWarn
	LevelError = slog.LevelError
)

// Logger wraps slog.Logger with ECS-compatible defaults.
type Logger struct {
	*slog.Logger
}

// Config holds logger configuration.
type Config struct {
	Level       slog.Level
	Output      io.Writer
	Environment string
}

// DefaultConfig returns default logger configuration.
func DefaultConfig() *Config {
	return &Config{
		Level:       LevelInfo,
		Output:      os.Stdout,
		Environment: getEnv(constants.EnvEnvironment, constants.DefaultEnvironment),
	}
}

// New creates a new ECS-compatible logger.
func New(cfg *Config) *Logger {
	if cfg == nil {
		cfg = DefaultConfig()
	}

	opts := &slog.HandlerOptions{
		Level: cfg.Level,
		ReplaceAttr: func(groups []string, a slog.Attr) slog.Attr {
			// ECS field mapping
			switch a.Key {
			case slog.TimeKey:
				return slog.Attr{Key: constants.ECSFieldTimestamp, Value: a.Value}
			case slog.LevelKey:
				return slog.Attr{Key: constants.ECSFieldLogLevel, Value: slog.StringValue(a.Value.String())}
			case slog.MessageKey:
				return a
			}
			return a
		},
	}

	handler := slog.NewJSONHandler(cfg.Output, opts)
	baseLogger := slog.New(handler)

	// Add ECS base fields
	ecsLogger := baseLogger.With(
		slog.Group("ecs",
			slog.String("version", constants.ECSVersion),
		),
		slog.Group("service",
			slog.String("name", constants.ServiceName),
			slog.String("version", constants.ServiceVersion),
			slog.String("environment", cfg.Environment),
		),
	)

	return &Logger{Logger: ecsLogger}
}

// WithContext returns a logger with context values (e.g., trace_id).
func (l *Logger) WithContext(ctx context.Context) *Logger {
	// Extract trace ID if available (from context or headers)
	// This can be extended to support OpenTelemetry trace context
	return l
}

// WithRequest returns a logger with HTTP request metadata.
func (l *Logger) WithRequest(method, path, host string) *Logger {
	return &Logger{
		Logger: l.With(
			slog.Group("http",
				slog.String("request.method", method),
				slog.String("url.path", path),
			),
			slog.String("host.name", host),
		),
	}
}

// WithTrace returns a logger with trace context from B3 headers.
func (l *Logger) WithTrace(traceID, spanID string) *Logger {
	if traceID == "" {
		return l
	}
	attrs := []any{
		slog.String(constants.ECSFieldTraceID, traceID),
	}
	if spanID != "" {
		attrs = append(attrs, slog.String(constants.ECSFieldSpanID, spanID))
	}
	return &Logger{
		Logger: l.With(attrs...),
	}
}

// WithUser returns a logger with user context (masked).
func (l *Logger) WithUser(userID, provider string) *Logger {
	return &Logger{
		Logger: l.With(
			slog.Group("user",
				slog.String("id", MaskUserID(userID)),
			),
			slog.String(constants.ECSFieldAuthProvider, provider),
		),
	}
}

// WithDuration returns a logger with duration information.
func (l *Logger) WithDuration(d time.Duration) *Logger {
	return &Logger{
		Logger: l.With(
			slog.Group("event",
				slog.Float64("duration_ms", float64(d.Microseconds())/1000),
			),
		),
	}
}

// TraceInfo holds B3 trace context.
type TraceInfo struct {
	TraceID string
	SpanID  string
}

// AuthAllow logs an allowed authorization request.
func (l *Logger) AuthAllow(method, path, host, userID, provider, jti string, duration time.Duration) {
	l.AuthAllowWithTrace(method, path, host, userID, provider, jti, duration, TraceInfo{})
}

// AuthAllowWithTrace logs an allowed authorization request with trace context.
func (l *Logger) AuthAllowWithTrace(method, path, host, userID, provider, jti string, duration time.Duration, trace TraceInfo) {
	l.WithTrace(trace.TraceID, trace.SpanID).
		WithRequest(method, path, host).
		WithUser(userID, provider).
		WithDuration(duration).
		Info("Authorization allowed",
			slog.String(constants.ECSFieldEventAction, constants.EventActionAuthorization),
			slog.String(constants.ECSFieldEventOutcome, constants.EventOutcomeSuccess),
			slog.String(constants.ECSFieldTokenJTI, MaskJTI(jti)),
		)
}

// AuthDeny logs a denied authorization request.
func (l *Logger) AuthDeny(method, path, host, reason string, duration time.Duration, err error) {
	l.AuthDenyWithTrace(method, path, host, reason, duration, err, TraceInfo{})
}

// AuthDenyWithTrace logs a denied authorization request with trace context.
func (l *Logger) AuthDenyWithTrace(method, path, host, reason string, duration time.Duration, err error, trace TraceInfo) {
	logger := l.WithTrace(trace.TraceID, trace.SpanID).
		WithRequest(method, path, host).
		WithDuration(duration)

	attrs := []any{
		slog.String(constants.ECSFieldEventAction, constants.EventActionAuthorization),
		slog.String(constants.ECSFieldEventOutcome, constants.EventOutcomeFailure),
		slog.String(constants.ECSFieldEventReason, reason),
	}

	if err != nil {
		attrs = append(attrs, slog.String(constants.ECSFieldErrorMessage, err.Error()))
	}

	logger.Warn("Authorization denied", attrs...)
}

// AuthDenyWithUser logs a denied authorization with user context.
func (l *Logger) AuthDenyWithUser(method, path, host, userID, jti, reason string, duration time.Duration, err error) {
	l.AuthDenyWithUserAndTrace(method, path, host, userID, jti, reason, duration, err, TraceInfo{})
}

// AuthDenyWithUserAndTrace logs a denied authorization with user context and trace.
func (l *Logger) AuthDenyWithUserAndTrace(method, path, host, userID, jti, reason string, duration time.Duration, err error, trace TraceInfo) {
	logger := l.WithTrace(trace.TraceID, trace.SpanID).
		WithRequest(method, path, host).
		WithUser(userID, "").
		WithDuration(duration)

	attrs := []any{
		slog.String(constants.ECSFieldEventAction, constants.EventActionAuthorization),
		slog.String(constants.ECSFieldEventOutcome, constants.EventOutcomeFailure),
		slog.String(constants.ECSFieldEventReason, reason),
		slog.String(constants.ECSFieldTokenJTI, MaskJTI(jti)),
	}

	if err != nil {
		attrs = append(attrs, slog.String(constants.ECSFieldErrorMessage, err.Error()))
	}

	logger.Warn("Authorization denied", attrs...)
}

// getEnv returns environment variable or default value.
func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

// Global logger instance
var defaultLogger *Logger

// Init initializes the global logger.
func Init(cfg *Config) {
	defaultLogger = New(cfg)
}

// Default returns the global logger.
func Default() *Logger {
	if defaultLogger == nil {
		defaultLogger = New(nil)
	}
	return defaultLogger
}

// ServiceName returns the service name constant (for external use).
func ServiceName() string {
	return constants.ServiceName
}

// ServiceVersion returns the service version constant (for external use).
func ServiceVersion() string {
	return constants.ServiceVersion
}

// NewTestLogger creates a logger for testing (discards output).
func NewTestLogger() *Logger {
	cfg := &Config{
		Level:       LevelDebug,
		Output:      io.Discard,
		Environment: "test",
	}
	return New(cfg)
}
