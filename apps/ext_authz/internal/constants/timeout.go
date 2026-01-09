package constants

import "time"

// ============================================================================
// Timeouts
// ============================================================================

const (
	// InitTimeout is the timeout for initialization (Redis connection, etc.)
	InitTimeout = 5 * time.Second

	// GracefulShutdownTimeout is the timeout for graceful shutdown
	GracefulShutdownTimeout = 10 * time.Second
)
