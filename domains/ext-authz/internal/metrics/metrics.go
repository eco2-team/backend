package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

const namespace = "ext_authz"

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
			Buckets:   []float64{.0005, .001, .0025, .005, .01, .025, .05, .1, .25, .5, 1},
		},
		[]string{"result", "reason"},
	)

	// JWTVerifyDuration: JWT signature verification time
	JWTVerifyDuration = promauto.NewHistogram(
		prometheus.HistogramOpts{
			Namespace: namespace,
			Name:      "jwt_verify_duration_seconds",
			Help:      "Time spent verifying JWT tokens",
			Buckets:   []float64{.0001, .00025, .0005, .001, .0025, .005, .01, .025, .05},
		},
	)

	// RedisLookupDuration: Blacklist lookup time (includes pool wait)
	RedisLookupDuration = promauto.NewHistogram(
		prometheus.HistogramOpts{
			Namespace: namespace,
			Name:      "redis_lookup_duration_seconds",
			Help:      "Time spent checking Redis blacklist",
			Buckets:   []float64{.0001, .00025, .0005, .001, .0025, .005, .01, .025, .05, .1},
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
