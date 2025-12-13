package server

import (
	"context"
	"log"
	"time"

	corev3 "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	authv3 "github.com/envoyproxy/go-control-plane/envoy/service/auth/v3"
	typev3 "github.com/envoyproxy/go-control-plane/envoy/type/v3"
	"google.golang.org/genproto/googleapis/rpc/code"
	"google.golang.org/genproto/googleapis/rpc/status"

	"github.com/eco2-team/backend/domains/ext-authz/internal/jwt"
	"github.com/eco2-team/backend/domains/ext-authz/internal/metrics"
	"github.com/eco2-team/backend/domains/ext-authz/internal/store"
)

type AuthorizationServer struct {
	verifier *jwt.Verifier
	store    *store.Store
}

func New(verifier *jwt.Verifier, store *store.Store) *AuthorizationServer {
	return &AuthorizationServer{
		verifier: verifier,
		store:    store,
	}
}

// extractRequestInfo extracts method, path, and host from the request
func extractRequestInfo(req *authv3.CheckRequest) (method, path, host string) {
	if req.Attributes != nil && req.Attributes.Request != nil && req.Attributes.Request.Http != nil {
		http := req.Attributes.Request.Http
		method = http.Method
		path = http.Path
		host = http.Host
	}
	return
}

// Check implements the authorization logic
func (s *AuthorizationServer) Check(ctx context.Context, req *authv3.CheckRequest) (*authv3.CheckResponse, error) {
	start := time.Now()
	metrics.RequestsInFlight.Inc()
	defer metrics.RequestsInFlight.Dec()

	method, path, host := extractRequestInfo(req)

	// Helper to record metrics on exit
	recordMetrics := func(result, reason string) {
		duration := time.Since(start).Seconds()
		metrics.RequestDuration.WithLabelValues(result, reason).Observe(duration)
		metrics.RequestsTotal.WithLabelValues(result, reason).Inc()
	}

	// 1. Extract Token
	authHeader, ok := req.Attributes.Request.Http.Headers["authorization"]
	if !ok || authHeader == "" {
		log.Printf("[DENY] method=%s path=%s host=%s reason=\"missing_auth_header\" duration=%s",
			method, path, host, time.Since(start))
		recordMetrics(metrics.ResultDeny, metrics.ReasonMissingHeader)
		return denyResponse(typev3.StatusCode_Unauthorized, "Missing Authorization header"), nil
	}

	// 2. Verify JWT
	jwtStart := time.Now()
	claims, err := s.verifier.Verify(authHeader)
	metrics.JWTVerifyDuration.Observe(time.Since(jwtStart).Seconds())

	if err != nil {
		log.Printf("[DENY] method=%s path=%s host=%s reason=\"invalid_token\" error=\"%v\" duration=%s",
			method, path, host, err, time.Since(start))
		recordMetrics(metrics.ResultDeny, metrics.ReasonInvalidToken)
		metrics.ErrorsTotal.WithLabelValues("jwt_verify").Inc()
		return denyResponse(typev3.StatusCode_Unauthorized, "Invalid token"), nil
	}

	// Extract user info for logging
	userID, _ := claims["sub"].(string)
	jti, _ := claims["jti"].(string)

	// 3. Check Blacklist
	if jti != "" {
		redisStart := time.Now()
		blacklisted, err := s.store.IsBlacklisted(ctx, jti)
		metrics.RedisLookupDuration.Observe(time.Since(redisStart).Seconds())

		if err != nil {
			log.Printf("[DENY] method=%s path=%s host=%s user_id=%s jti=%s reason=\"redis_error\" error=\"%v\" duration=%s",
				method, path, host, userID, jti, err, time.Since(start))
			recordMetrics(metrics.ResultDeny, metrics.ReasonRedisError)
			metrics.ErrorsTotal.WithLabelValues("redis").Inc()
			// Fail-closed: Deny on internal error
			return denyResponse(typev3.StatusCode_InternalServerError, "Internal Authorization Error"), nil
		}
		if blacklisted {
			log.Printf("[DENY] method=%s path=%s host=%s user_id=%s jti=%s reason=\"blacklisted\" duration=%s",
				method, path, host, userID, jti, time.Since(start))
			recordMetrics(metrics.ResultDeny, metrics.ReasonBlacklisted)
			metrics.BlacklistHits.Inc()
			return denyResponse(typev3.StatusCode_Forbidden, "Token is blacklisted"), nil
		}
	}

	// 4. Allow Request (Inject Headers)
	provider, _ := claims["provider"].(string)
	log.Printf("[ALLOW] method=%s path=%s host=%s user_id=%s provider=%s jti=%s duration=%s",
		method, path, host, userID, provider, jti, time.Since(start))
	recordMetrics(metrics.ResultAllow, metrics.ReasonSuccess)
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
							Key:   "x-user-id",
							Value: userID,
						},
					},
					{
						Header: &corev3.HeaderValue{
							Key:   "x-auth-provider",
							Value: provider,
						},
					},
				},
			},
		},
	}
}

func denyResponse(statusCode typev3.StatusCode, body string) *authv3.CheckResponse {
	return &authv3.CheckResponse{
		Status: &status.Status{
			Code: int32(code.Code_PERMISSION_DENIED),
		},
		HttpResponse: &authv3.CheckResponse_DeniedResponse{
			DeniedResponse: &authv3.DeniedHttpResponse{
				Status: &typev3.HttpStatus{
					Code: statusCode,
				},
				Body: body,
			},
		},
	}
}
