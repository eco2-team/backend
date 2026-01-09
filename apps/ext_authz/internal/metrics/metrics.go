package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

const namespace = "ext_authz"

// ============================================================================
// Histogram bucket configurations
// ============================================================================
//
// Using ExponentialBucketsRange for fine-grained latency measurement:
// - Denser buckets at lower latencies (where most requests fall)
// - Sparser buckets at higher latencies (tail detection)

const (
	// Request duration: 0.5ms ~ 2s (full auth check including JWT + Redis)
	requestDurationMin    = 0.0005 // 0.5ms
	requestDurationMax    = 2.0    // 2s
	requestDurationCount  = 14     // ~2x factor between buckets

	// JWT verification: 0.1ms ~ 100ms (CPU-bound crypto operation)
	jwtVerifyMin   = 0.0001 // 0.1ms
	jwtVerifyMax   = 0.1    // 100ms
	jwtVerifyCount = 10     // ~2x factor

	// Redis lookup: 1ms ~ 5s (network + pool wait)
	redisLookupMin   = 0.001 // 1ms
	redisLookupMax   = 5.0   // 5s (covers timeout scenarios)
	redisLookupCount = 12    // ~2x factor
)

// ============================================================================
// Histograms - Latency measurements
// ============================================================================

var (
	// RequestDuration: Total time to process an auth check (p50, p95, p99)
	// Labels: result (allow/deny), reason (success/missing_header/invalid_token/...)
	RequestDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Namespace: namespace,
			Name:      "request_duration_seconds",
			Help:      "Time spent processing authorization requests",
			Buckets:   prometheus.ExponentialBucketsRange(requestDurationMin, requestDurationMax, requestDurationCount),
		},
		[]string{"result", "reason"},
	)

	// JWTVerifyDuration: JWT signature verification time
	JWTVerifyDuration = promauto.NewHistogram(
		prometheus.HistogramOpts{
			Namespace: namespace,
			Name:      "jwt_verify_duration_seconds",
			Help:      "Time spent verifying JWT tokens",
			Buckets:   prometheus.ExponentialBucketsRange(jwtVerifyMin, jwtVerifyMax, jwtVerifyCount),
		},
	)

	// RedisLookupDuration: Blacklist lookup time (includes pool wait)
	RedisLookupDuration = promauto.NewHistogram(
		prometheus.HistogramOpts{
			Namespace: namespace,
			Name:      "redis_lookup_duration_seconds",
			Help:      "Time spent checking Redis blacklist",
			Buckets:   prometheus.ExponentialBucketsRange(redisLookupMin, redisLookupMax, redisLookupCount),
		},
	)
)

// ============================================================================
// Counters - Request/Error counts
// ============================================================================

var (
	// RequestsTotal: Total requests by result and reason
	RequestsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Namespace: namespace,
			Name:      "requests_total",
			Help:      "Total number of authorization requests",
		},
		[]string{"result", "reason"},
	)

	// ErrorsTotal: Errors by type (jwt_verify, redis)
	ErrorsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Namespace: namespace,
			Name:      "errors_total",
			Help:      "Total number of errors by type",
		},
		[]string{"type"},
	)

	// BlacklistHits: Tokens rejected due to blacklist
	BlacklistHits = promauto.NewCounter(
		prometheus.CounterOpts{
			Namespace: namespace,
			Name:      "blacklist_hits_total",
			Help:      "Total number of blacklisted tokens detected",
		},
	)
)

// ============================================================================
// Gauges - Current state
// ============================================================================

var (
	// RequestsInFlight: Concurrent requests being processed
	RequestsInFlight = promauto.NewGauge(
		prometheus.GaugeOpts{
			Namespace: namespace,
			Name:      "requests_in_flight",
			Help:      "Number of authorization requests currently being processed",
		},
	)
)

// ============================================================================
// Label constants
// ============================================================================

// Result labels for RequestDuration and RequestsTotal
const (
	ResultAllow = "allow"
	ResultDeny  = "deny"
)

// Reason labels for RequestDuration and RequestsTotal
const (
	ReasonSuccess       = "success"
	ReasonMissingHeader = "missing_header"
	ReasonInvalidToken  = "invalid_token"
	ReasonBlacklisted   = "blacklisted"
	ReasonRedisError    = "redis_error"
)

// Error type labels for ErrorsTotal
const (
	ErrorTypeJWTVerify = "jwt_verify"
	ErrorTypeRedis     = "redis"
)
