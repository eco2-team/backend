package logging

import (
	"strings"

	"github.com/eco2-team/backend/domains/ext-authz/internal/constants"
)

// MaskJTI masks a JWT ID, preserving first and last characters.
// Example: "abc123def456" -> "abc1...f456"
func MaskJTI(jti string) string {
	return maskPartial(jti)
}

// MaskUserID masks a user ID for logging.
// UUIDs are partially masked, short IDs are fully masked.
// Example: "550e8400-e29b-41d4-a716-446655440000" -> "550e...0000"
func MaskUserID(userID string) string {
	return maskPartial(userID)
}

// MaskToken masks a JWT token, preserving only prefix.
// Example: "eyJhbGciOiJIUzI1NiJ9.xxx" -> "eyJh...REDACTED"
func MaskToken(token string) string {
	if token == "" {
		return constants.MaskPlaceholder
	}

	// For tokens, only show first few chars
	if len(token) > constants.MaskPreserveLen {
		return token[:constants.MaskPreserveLen] + constants.MaskSeparator + constants.MaskPlaceholder
	}
	return constants.MaskPlaceholder
}

// maskPartial applies partial masking to a string.
// If the string is shorter than MaskMinLength, it's fully masked.
// Otherwise, first and last MaskPreserveLen characters are preserved.
func maskPartial(s string) string {
	if s == "" {
		return constants.MaskPlaceholder
	}

	// Remove any "Bearer " prefix
	s = strings.TrimPrefix(s, constants.BearerPrefix)
	s = strings.TrimPrefix(s, constants.BearerPrefixLower)

	if len(s) < constants.MaskMinLength {
		return constants.MaskPlaceholder
	}

	prefix := s[:constants.MaskPreserveLen]
	suffix := s[len(s)-constants.MaskPreserveLen:]
	return prefix + constants.MaskSeparator + suffix
}

// IsSensitiveKey checks if a key name indicates sensitive data.
// Aligned with Python SENSITIVE_FIELD_PATTERNS.
func IsSensitiveKey(key string) bool {
	lower := strings.ToLower(key)
	for _, pattern := range constants.SensitivePatterns {
		if strings.Contains(lower, pattern) {
			return true
		}
	}
	return false
}
