package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

const (
	namespace = "ext_authz"
)

var (
	// RequestDuration measures the total time to process an auth check request
	RequestDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Namespace: namespace,
			Name:      "request_duration_seconds",
			Help:      "Time spent processing authorization requests",
			Buckets:   []float64{.0005, .001, .0025, .005, .01, .025, .05, .1, .25, .5, 1},
		},
		[]string{"result", "reason"},
	)

	// JWTVerifyDuration measures JWT verification time
	JWTVerifyDuration = promauto.NewHistogram(
		prometheus.HistogramOpts{
			Namespace: namespace,
			Name:      "jwt_verify_duration_seconds",
			Help:      "Time spent verifying JWT tokens",
			Buckets:   []float64{.0001, .00025, .0005, .001, .0025, .005, .01, .025, .05},
		},
	)

	// RedisLookupDuration measures Redis blacklist lookup time
	RedisLookupDuration = promauto.NewHistogram(
		prometheus.HistogramOpts{
			Namespace: namespace,
			Name:      "redis_lookup_duration_seconds",
			Help:      "Time spent checking Redis blacklist",
			Buckets:   []float64{.0001, .00025, .0005, .001, .0025, .005, .01, .025, .05, .1},
		},
	)

	// RequestsTotal counts total requests by result
	RequestsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Namespace: namespace,
			Name:      "requests_total",
			Help:      "Total number of authorization requests",
		},
		[]string{"result", "reason"},
	)

	// RequestsInFlight tracks concurrent requests
	RequestsInFlight = promauto.NewGauge(
		prometheus.GaugeOpts{
			Namespace: namespace,
			Name:      "requests_in_flight",
			Help:      "Number of authorization requests currently being processed",
		},
	)

	// ErrorsTotal counts errors by type
	ErrorsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Namespace: namespace,
			Name:      "errors_total",
			Help:      "Total number of errors by type",
		},
		[]string{"type"},
	)

	// BlacklistHits counts blacklist hits
	BlacklistHits = promauto.NewCounter(
		prometheus.CounterOpts{
			Namespace: namespace,
			Name:      "blacklist_hits_total",
			Help:      "Total number of blacklisted tokens detected",
		},
	)
)

// Result constants for labeling
const (
	ResultAllow = "allow"
	ResultDeny  = "deny"

	ReasonSuccess       = "success"
	ReasonMissingHeader = "missing_header"
	ReasonInvalidToken  = "invalid_token"
	ReasonBlacklisted   = "blacklisted"
	ReasonRedisError    = "redis_error"
)
