// Package constants provides centralized constant definitions for ext-authz.
package constants

// ============================================================================
// HTTP Headers
// ============================================================================

const (
	// Request headers
	HeaderAuthorization = "authorization"

	// Response headers (injected to upstream)
	HeaderUserID       = "x-user-id"
	HeaderAuthProvider = "x-auth-provider"

	// B3 Trace Context headers (Istio/Envoy)
	HeaderB3TraceID      = "x-b3-traceid"
	HeaderB3SpanID       = "x-b3-spanid"
	HeaderB3Sampled      = "x-b3-sampled"
	HeaderB3ParentSpanID = "x-b3-parentspanid"
)

// ============================================================================
// HTTP Response Messages
// ============================================================================

const (
	// Error response bodies
	MsgMalformedRequest = "Malformed request"
	MsgMissingAuthHeader = "Missing Authorization header"
	MsgInvalidToken      = "Invalid token"
	MsgInternalError     = "Internal Authorization Error"
	MsgBlacklisted       = "Token is blacklisted"
)

// ============================================================================
// HTTP Paths
// ============================================================================

const (
	PathMetrics = "/metrics"
	PathHealth  = "/health"
	PathReady   = "/ready"
)

// ============================================================================
// Health Check
// ============================================================================

const (
	HealthOK = "ok"
)
