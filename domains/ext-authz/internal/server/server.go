package server

import (
	"context"
	"errors"
	"time"

	corev3 "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	authv3 "github.com/envoyproxy/go-control-plane/envoy/service/auth/v3"
	typev3 "github.com/envoyproxy/go-control-plane/envoy/type/v3"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	semconv "go.opentelemetry.io/otel/semconv/v1.26.0"
	"go.opentelemetry.io/otel/trace"
	"google.golang.org/genproto/googleapis/rpc/code"
	"google.golang.org/genproto/googleapis/rpc/status"
	"google.golang.org/grpc/metadata"

	"github.com/eco2-team/backend/domains/ext-authz/internal/constants"
	"github.com/eco2-team/backend/domains/ext-authz/internal/jwt"
	"github.com/eco2-team/backend/domains/ext-authz/internal/logging"
	"github.com/eco2-team/backend/domains/ext-authz/internal/metrics"
)

// CORSConfig holds CORS configuration for deny responses
type CORSConfig struct {
	AllowedOrigins map[string]bool
}

// ============================================================================
// Interfaces (Dependency Inversion)
// ============================================================================

// TokenVerifier verifies JWT tokens and returns claims.
type TokenVerifier interface {
	Verify(tokenString string) (map[string]any, error)
}

// BlacklistStore checks if a token is blacklisted.
type BlacklistStore interface {
	IsBlacklisted(ctx context.Context, jti string) (bool, error)
}

// ============================================================================
// AuthorizationServer
// ============================================================================

type AuthorizationServer struct {
	verifier   TokenVerifier
	store      BlacklistStore
	logger     *logging.Logger
	corsConfig *CORSConfig
}

func New(verifier TokenVerifier, store BlacklistStore, allowedOrigins []string) (*AuthorizationServer, error) {
	if verifier == nil {
		return nil, errors.New(constants.ErrVerifierRequired)
	}
	if store == nil {
		return nil, errors.New(constants.ErrStoreRequired)
	}

	// Build CORS config as a set for O(1) lookup
	corsConfig := &CORSConfig{
		AllowedOrigins: make(map[string]bool, len(allowedOrigins)),
	}
	for _, origin := range allowedOrigins {
		corsConfig.AllowedOrigins[origin] = true
	}

	return &AuthorizationServer{
		verifier:   verifier,
		store:      store,
		logger:     logging.Default(),
		corsConfig: corsConfig,
	}, nil
}

// extractRequestInfo extracts method, path, host, and origin from the request
func extractRequestInfo(req *authv3.CheckRequest) (method, path, host, origin string) {
	if req.Attributes != nil && req.Attributes.Request != nil && req.Attributes.Request.Http != nil {
		http := req.Attributes.Request.Http
		method = http.Method
		path = http.Path
		host = http.Host
		origin = http.Headers["origin"]
	}
	return
}

// httpHeaderCarrier adapts HTTP headers from CheckRequest for trace propagation
type httpHeaderCarrier map[string]string

func (c httpHeaderCarrier) Get(key string) string {
	return c[key]
}

func (c httpHeaderCarrier) Set(key, value string) {
	c[key] = value
}

func (c httpHeaderCarrier) Keys() []string {
	keys := make([]string, 0, len(c))
	for k := range c {
		keys = append(keys, k)
	}
	return keys
}

// extractTraceContext extracts trace context from HTTP headers in CheckRequest
// and returns a context with the trace information injected.
// This is necessary because Istio passes trace headers in CheckRequest body,
// not in gRPC metadata, so otelgrpc interceptor cannot extract them.
func extractTraceContext(ctx context.Context, req *authv3.CheckRequest) context.Context {
	if req.Attributes == nil || req.Attributes.Request == nil || req.Attributes.Request.Http == nil {
		return ctx
	}

	headers := req.Attributes.Request.Http.Headers
	if headers == nil {
		return ctx
	}

	// Use OTEL propagator to extract trace context from HTTP headers
	propagator := otel.GetTextMapPropagator()
	return propagator.Extract(ctx, httpHeaderCarrier(headers))
}

// extractTraceInfo extracts B3 trace context from gRPC metadata or HTTP headers
// Priority: 1. gRPC metadata (from Istio sidecar) 2. HTTP headers (from client)
func extractTraceInfo(ctx context.Context, req *authv3.CheckRequest) logging.TraceInfo {
	traceInfo := logging.TraceInfo{}

	// 1. Try gRPC metadata first (Istio sidecar injects trace context here)
	if md, ok := metadata.FromIncomingContext(ctx); ok {
		if vals := md.Get(constants.HeaderB3TraceID); len(vals) > 0 {
			traceInfo.TraceID = vals[0]
		}
		if vals := md.Get(constants.HeaderB3SpanID); len(vals) > 0 {
			traceInfo.SpanID = vals[0]
		}
	}

	// 2. Fallback to HTTP headers (if client sent them)
	if traceInfo.TraceID == "" && req.Attributes != nil && req.Attributes.Request != nil && req.Attributes.Request.Http != nil {
		headers := req.Attributes.Request.Http.Headers
		if val := headers[constants.HeaderB3TraceID]; val != "" {
			traceInfo.TraceID = val
		}
		if val := headers[constants.HeaderB3SpanID]; val != "" {
			traceInfo.SpanID = val
		}
	}

	// 3. Try to get from OTEL span context (if span was created)
	if traceInfo.TraceID == "" {
		spanCtx := trace.SpanContextFromContext(ctx)
		if spanCtx.IsValid() {
			traceInfo.TraceID = spanCtx.TraceID().String()
			traceInfo.SpanID = spanCtx.SpanID().String()
		}
	}

	return traceInfo
}

// Check implements the authorization logic
func (s *AuthorizationServer) Check(ctx context.Context, req *authv3.CheckRequest) (*authv3.CheckResponse, error) {
	start := time.Now()
	metrics.RequestsInFlight.Inc()
	defer metrics.RequestsInFlight.Dec()

	method, path, host, origin := extractRequestInfo(req)

	// Check if origin is allowed for CORS headers in deny responses
	allowedOrigin := ""
	if origin != "" && s.corsConfig.AllowedOrigins[origin] {
		allowedOrigin = origin
	}

	// Extract trace context from HTTP headers in CheckRequest body
	// (Istio passes trace headers here, not in gRPC metadata)
	ctx = extractTraceContext(ctx, req)

	// Start span for authorization check
	tracer := otel.Tracer("ext-authz")
	ctx, span := tracer.Start(ctx, "Authorization.Check",
		trace.WithSpanKind(trace.SpanKindServer),
		trace.WithAttributes(
			semconv.RPCSystemGRPC,
			semconv.RPCService("envoy.service.auth.v3.Authorization"),
			semconv.RPCMethod("Check"),
			semconv.HTTPRequestMethodKey.String(method),
			semconv.URLPath(path),
			attribute.String("http.host", host),
		),
	)
	defer span.End()

	traceInfo := extractTraceInfo(ctx, req)

	// Helper to record metrics and span status on exit
	recordMetrics := func(result, reason string) {
		duration := time.Since(start).Seconds()
		metrics.RequestDuration.WithLabelValues(result, reason).Observe(duration)
		metrics.RequestsTotal.WithLabelValues(result, reason).Inc()
	}

	// CORS Preflight: OPTIONS 요청은 인증 없이 허용
	if method == "OPTIONS" {
		s.logger.Info("CORS preflight request allowed", "method", method, "path", path, "host", host)
		recordMetrics(metrics.ResultAllow, "cors_preflight")
		span.SetAttributes(attribute.String("authz.result", "allow"), attribute.String("authz.reason", "cors_preflight"))
		return allowCORSPreflightResponse(), nil
	}

	// 1. Extract Token
	if req.Attributes == nil || req.Attributes.Request == nil || req.Attributes.Request.Http == nil {
		s.logger.AuthDenyWithTrace(method, path, host, constants.ReasonMalformedRequest, time.Since(start), nil, traceInfo)
		recordMetrics(metrics.ResultDeny, metrics.ReasonMissingHeader)
		span.SetStatus(codes.Error, constants.ReasonMalformedRequest)
		span.SetAttributes(attribute.String("authz.result", "deny"), attribute.String("authz.reason", "malformed_request"))
		return denyResponse(typev3.StatusCode_BadRequest, constants.MsgMalformedRequest, allowedOrigin), nil
	}

	authHeader, ok := req.Attributes.Request.Http.Headers[constants.HeaderAuthorization]
	if !ok || authHeader == "" {
		s.logger.AuthDenyWithTrace(method, path, host, constants.ReasonMissingHeader, time.Since(start), nil, traceInfo)
		recordMetrics(metrics.ResultDeny, metrics.ReasonMissingHeader)
		span.SetStatus(codes.Error, constants.ReasonMissingHeader)
		span.SetAttributes(attribute.String("authz.result", "deny"), attribute.String("authz.reason", "missing_auth_header"))
		return denyResponse(typev3.StatusCode_Unauthorized, constants.MsgMissingAuthHeader, allowedOrigin), nil
	}

	// 2. Verify JWT
	jwtStart := time.Now()
	claims, err := s.verifier.Verify(authHeader)
	metrics.JWTVerifyDuration.Observe(time.Since(jwtStart).Seconds())

	if err != nil {
		s.logger.AuthDenyWithTrace(method, path, host, constants.ReasonInvalidToken, time.Since(start), err, traceInfo)
		recordMetrics(metrics.ResultDeny, metrics.ReasonInvalidToken)
		metrics.ErrorsTotal.WithLabelValues(metrics.ErrorTypeJWTVerify).Inc()
		span.RecordError(err)
		span.SetStatus(codes.Error, constants.ReasonInvalidToken)
		span.SetAttributes(attribute.String("authz.result", "deny"), attribute.String("authz.reason", "invalid_token"))
		return denyResponse(typev3.StatusCode_Unauthorized, constants.MsgInvalidToken, allowedOrigin), nil
	}

	// Extract user info for logging
	userID, _ := claims[jwt.ClaimSub].(string)
	jti, _ := claims[jwt.ClaimJTI].(string)
	span.SetAttributes(attribute.String("user.id", userID))

	// 3. Check Blacklist
	if jti != "" {
		redisStart := time.Now()
		blacklisted, err := s.store.IsBlacklisted(ctx, jti)
		metrics.RedisLookupDuration.Observe(time.Since(redisStart).Seconds())

		if err != nil {
			s.logger.AuthDenyWithUserAndTrace(method, path, host, userID, jti, constants.ReasonRedisError, time.Since(start), err, traceInfo)
			recordMetrics(metrics.ResultDeny, metrics.ReasonRedisError)
			metrics.ErrorsTotal.WithLabelValues(metrics.ErrorTypeRedis).Inc()
			span.RecordError(err)
			span.SetStatus(codes.Error, constants.ReasonRedisError)
			span.SetAttributes(attribute.String("authz.result", "deny"), attribute.String("authz.reason", "redis_error"))
			// Fail-closed: Deny on internal error
			return denyResponse(typev3.StatusCode_InternalServerError, constants.MsgInternalError, allowedOrigin), nil
		}
		if blacklisted {
			s.logger.AuthDenyWithUserAndTrace(method, path, host, userID, jti, constants.ReasonBlacklisted, time.Since(start), nil, traceInfo)
			recordMetrics(metrics.ResultDeny, metrics.ReasonBlacklisted)
			metrics.BlacklistHits.Inc()
			span.SetStatus(codes.Error, constants.ReasonBlacklisted)
			span.SetAttributes(attribute.String("authz.result", "deny"), attribute.String("authz.reason", "blacklisted"))
			return denyResponse(typev3.StatusCode_Forbidden, constants.MsgBlacklisted, allowedOrigin), nil
		}
	}

	// 4. Allow Request (Inject Headers)
	provider, _ := claims[jwt.ClaimProvider].(string)
	s.logger.AuthAllowWithTrace(method, path, host, userID, provider, jti, time.Since(start), traceInfo)
	recordMetrics(metrics.ResultAllow, metrics.ReasonSuccess)
	span.SetStatus(codes.Ok, "authorized")
	span.SetAttributes(
		attribute.String("authz.result", "allow"),
		attribute.String("authz.reason", "success"),
		attribute.String("auth.provider", provider),
	)
	return allowResponse(userID, provider), nil
}

func allowResponse(userID, provider string) *authv3.CheckResponse {
	return &authv3.CheckResponse{
		Status: &status.Status{
			Code: int32(code.Code_OK),
		},
		HttpResponse: &authv3.CheckResponse_OkResponse{
			OkResponse: &authv3.OkHttpResponse{
				Headers: []*corev3.HeaderValueOption{
					{
						Header: &corev3.HeaderValue{
							Key:   constants.HeaderUserID,
							Value: userID,
						},
					},
					{
						Header: &corev3.HeaderValue{
							Key:   constants.HeaderAuthProvider,
							Value: provider,
						},
					},
				},
			},
		},
	}
}

func denyResponse(statusCode typev3.StatusCode, body string, allowedOrigin string) *authv3.CheckResponse {
	var headers []*corev3.HeaderValueOption

	// Add CORS headers if origin is allowed (prevents CORS error on 401/403)
	if allowedOrigin != "" {
		headers = []*corev3.HeaderValueOption{
			{
				Header: &corev3.HeaderValue{
					Key:   "Access-Control-Allow-Origin",
					Value: allowedOrigin,
				},
			},
			{
				Header: &corev3.HeaderValue{
					Key:   "Access-Control-Allow-Credentials",
					Value: "true",
				},
			},
		}
	}

	return &authv3.CheckResponse{
		Status: &status.Status{
			Code: int32(code.Code_PERMISSION_DENIED),
		},
		HttpResponse: &authv3.CheckResponse_DeniedResponse{
			DeniedResponse: &authv3.DeniedHttpResponse{
				Status: &typev3.HttpStatus{
					Code: statusCode,
				},
				Headers: headers,
				Body:    body,
			},
		},
	}
}

// allowCORSPreflightResponse returns an OK response for CORS preflight requests
// This allows the browser to proceed with the actual request after the preflight
func allowCORSPreflightResponse() *authv3.CheckResponse {
	return &authv3.CheckResponse{
		Status: &status.Status{
			Code: int32(code.Code_OK),
		},
		HttpResponse: &authv3.CheckResponse_OkResponse{
			OkResponse: &authv3.OkHttpResponse{
				// No custom headers needed for preflight
				// The actual CORS headers will be added by the backend FastAPI CORSMiddleware
			},
		},
	}
}
