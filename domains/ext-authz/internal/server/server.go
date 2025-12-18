package server

import (
	"context"
	"errors"
	"time"

	corev3 "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	authv3 "github.com/envoyproxy/go-control-plane/envoy/service/auth/v3"
	typev3 "github.com/envoyproxy/go-control-plane/envoy/type/v3"
	"google.golang.org/genproto/googleapis/rpc/code"
	"google.golang.org/genproto/googleapis/rpc/status"

	"github.com/eco2-team/backend/domains/ext-authz/internal/constants"
	"github.com/eco2-team/backend/domains/ext-authz/internal/jwt"
	"github.com/eco2-team/backend/domains/ext-authz/internal/logging"
	"github.com/eco2-team/backend/domains/ext-authz/internal/metrics"
)

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
	verifier TokenVerifier
	store    BlacklistStore
	logger   *logging.Logger
}

func New(verifier TokenVerifier, store BlacklistStore) (*AuthorizationServer, error) {
	if verifier == nil {
		return nil, errors.New(constants.ErrVerifierRequired)
	}
	if store == nil {
		return nil, errors.New(constants.ErrStoreRequired)
	}
	return &AuthorizationServer{
		verifier: verifier,
		store:    store,
		logger:   logging.Default(),
	}, nil
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

	// CORS Preflight: OPTIONS 요청은 인증 없이 허용
	if method == "OPTIONS" {
		s.logger.Info("CORS preflight request allowed", "method", method, "path", path, "host", host)
		recordMetrics(metrics.ResultAllow, "cors_preflight")
		return allowCORSPreflightResponse(), nil
	}

	// 1. Extract Token
	if req.Attributes == nil || req.Attributes.Request == nil || req.Attributes.Request.Http == nil {
		s.logger.AuthDeny(method, path, host, constants.ReasonMalformedRequest, time.Since(start), nil)
		recordMetrics(metrics.ResultDeny, metrics.ReasonMissingHeader)
		return denyResponse(typev3.StatusCode_BadRequest, constants.MsgMalformedRequest), nil
	}

	authHeader, ok := req.Attributes.Request.Http.Headers[constants.HeaderAuthorization]
	if !ok || authHeader == "" {
		s.logger.AuthDeny(method, path, host, constants.ReasonMissingHeader, time.Since(start), nil)
		recordMetrics(metrics.ResultDeny, metrics.ReasonMissingHeader)
		return denyResponse(typev3.StatusCode_Unauthorized, constants.MsgMissingAuthHeader), nil
	}

	// 2. Verify JWT
	jwtStart := time.Now()
	claims, err := s.verifier.Verify(authHeader)
	metrics.JWTVerifyDuration.Observe(time.Since(jwtStart).Seconds())

	if err != nil {
		s.logger.AuthDeny(method, path, host, constants.ReasonInvalidToken, time.Since(start), err)
		recordMetrics(metrics.ResultDeny, metrics.ReasonInvalidToken)
		metrics.ErrorsTotal.WithLabelValues(metrics.ErrorTypeJWTVerify).Inc()
		return denyResponse(typev3.StatusCode_Unauthorized, constants.MsgInvalidToken), nil
	}

	// Extract user info for logging
	userID, _ := claims[jwt.ClaimSub].(string)
	jti, _ := claims[jwt.ClaimJTI].(string)

	// 3. Check Blacklist
	if jti != "" {
		redisStart := time.Now()
		blacklisted, err := s.store.IsBlacklisted(ctx, jti)
		metrics.RedisLookupDuration.Observe(time.Since(redisStart).Seconds())

		if err != nil {
			s.logger.AuthDenyWithUser(method, path, host, userID, jti, constants.ReasonRedisError, time.Since(start), err)
			recordMetrics(metrics.ResultDeny, metrics.ReasonRedisError)
			metrics.ErrorsTotal.WithLabelValues(metrics.ErrorTypeRedis).Inc()
			// Fail-closed: Deny on internal error
			return denyResponse(typev3.StatusCode_InternalServerError, constants.MsgInternalError), nil
		}
		if blacklisted {
			s.logger.AuthDenyWithUser(method, path, host, userID, jti, constants.ReasonBlacklisted, time.Since(start), nil)
			recordMetrics(metrics.ResultDeny, metrics.ReasonBlacklisted)
			metrics.BlacklistHits.Inc()
			return denyResponse(typev3.StatusCode_Forbidden, constants.MsgBlacklisted), nil
		}
	}

	// 4. Allow Request (Inject Headers)
	provider, _ := claims[jwt.ClaimProvider].(string)
	s.logger.AuthAllow(method, path, host, userID, provider, jti, time.Since(start))
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
