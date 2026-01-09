package constants

// ============================================================================
// ECS (Elastic Common Schema) Field Keys
// ============================================================================
//
// Reference: https://www.elastic.co/guide/en/ecs/current/ecs-field-reference.html

const (
	// Base fields
	ECSFieldTimestamp = "@timestamp"
	ECSFieldMessage   = "message"

	// Log fields
	ECSFieldLogLevel = "log.level"

	// Service fields
	ECSFieldServiceName        = "service.name"
	ECSFieldServiceVersion     = "service.version"
	ECSFieldServiceEnvironment = "service.environment"

	// Event fields
	ECSFieldEventAction   = "event.action"
	ECSFieldEventOutcome  = "event.outcome"
	ECSFieldEventReason   = "event.reason"
	ECSFieldEventDuration = "event.duration_ms"

	// HTTP fields
	ECSFieldHTTPMethod = "http.request.method"
	ECSFieldURLPath    = "url.path"
	ECSFieldHostName   = "host.name"

	// User fields
	ECSFieldUserID = "user.id"

	// Error fields
	ECSFieldErrorMessage = "error.message"

	// Auth fields (custom)
	ECSFieldAuthProvider = "auth.provider"
	ECSFieldTokenJTI     = "token.jti"

	// Trace fields (ECS standard)
	ECSFieldTraceID = "trace.id"
	ECSFieldSpanID  = "span.id"
)

// ============================================================================
// ECS Event Actions
// ============================================================================

const (
	EventActionAuthorization = "authorization"
)

// ============================================================================
// ECS Event Outcomes
// ============================================================================

const (
	EventOutcomeSuccess = "success"
	EventOutcomeFailure = "failure"
)

// ============================================================================
// ECS Version
// ============================================================================

const (
	ECSVersion = "8.11"
)
