package constants

// ============================================================================
// Masking Configuration
// ============================================================================
//
// Aligned with Python implementation (domains/*/core/constants.py)

const (
	// MaskPlaceholder is the string used to replace fully masked values
	MaskPlaceholder = "***REDACTED***"

	// MaskPreserveLen is the number of characters to preserve at start/end
	MaskPreserveLen = 4

	// MaskMinLength is the minimum length for partial masking
	// Values shorter than this are fully masked
	MaskMinLength = 10

	// MaskSeparator is the separator between preserved prefix and suffix
	MaskSeparator = "..."
)

// ============================================================================
// Token Prefixes
// ============================================================================

const (
	BearerPrefix      = "Bearer "
	BearerPrefixLower = "bearer "
)

// ============================================================================
// Sensitive Field Patterns
// ============================================================================
//
// Aligned with Python SENSITIVE_FIELD_PATTERNS

var SensitivePatterns = []string{
	"password",
	"secret",
	"token",
	"api_key",
	"authorization",
}
