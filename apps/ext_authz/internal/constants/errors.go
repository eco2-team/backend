package constants

// ============================================================================
// Validation Error Messages
// ============================================================================

const (
	ErrVerifierRequired = "verifier is required"
	ErrStoreRequired    = "store is required"
	ErrSecretKeyRequired = "secretKey is required"
	ErrAlgorithmRequired = "algorithm is required"
)

// ============================================================================
// JWT Error Messages
// ============================================================================

const (
	ErrInvalidToken        = "invalid token: %w"
	ErrInvalidTokenClaims  = "invalid token claims"
	ErrMissingClaimSub     = "missing required claim: sub"
	ErrMissingClaimJTI     = "missing required claim: jti"
	ErrInvalidIssuer       = "invalid issuer: %v"
	ErrInvalidAudience     = "invalid audience: %v"
	ErrMissingScopePattern = "required scope missing: %s"
)

// ============================================================================
// Redis Error Messages
// ============================================================================

const (
	ErrPoolOptionsRequired = "pool options is required"
	ErrRedisURLParse       = "failed to parse redis url: %w"
	ErrRedisConnect        = "failed to connect to redis: %w"
	ErrRedisClientNil      = "redis client is nil"
	ErrStoreNil            = "store is nil"
	ErrRedisOperation      = "redis error: %w"
)

// ============================================================================
// Denial Reasons (for logging)
// ============================================================================

const (
	ReasonMalformedRequest = "malformed_request"
	ReasonMissingHeader    = "missing_auth_header"
	ReasonInvalidToken     = "invalid_token"
	ReasonRedisError       = "redis_error"
	ReasonBlacklisted      = "blacklisted"
)
