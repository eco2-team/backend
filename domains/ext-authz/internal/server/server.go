package server

import (
	"context"
	"log"

	corev3 "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	authv3 "github.com/envoyproxy/go-control-plane/envoy/service/auth/v3"
	typev3 "github.com/envoyproxy/go-control-plane/envoy/type/v3"
	"google.golang.org/genproto/googleapis/rpc/code"
	"google.golang.org/genproto/googleapis/rpc/status"

	"github.com/eco2-team/backend/domains/ext-authz/internal/jwt"
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

// Check implements the authorization logic
func (s *AuthorizationServer) Check(ctx context.Context, req *authv3.CheckRequest) (*authv3.CheckResponse, error) {
	// 1. Extract Token
	authHeader, ok := req.Attributes.Request.Http.Headers["authorization"]
	if !ok || authHeader == "" {
		return denyResponse(typev3.StatusCode_Unauthorized, "Missing Authorization header"), nil
	}

	// 2. Verify JWT
	claims, err := s.verifier.Verify(authHeader)
	if err != nil {
		log.Printf("[Check] Invalid token: %v", err)
		return denyResponse(typev3.StatusCode_Unauthorized, "Invalid token"), nil
	}

	// 3. Check Blacklist
	jti, ok := claims["jti"].(string)
	if ok {
		blacklisted, err := s.store.IsBlacklisted(ctx, jti)
		if err != nil {
			log.Printf("[Check] Redis error: %v", err)
			// Fail-closed: Deny on internal error
			return denyResponse(typev3.StatusCode_InternalServerError, "Internal Authorization Error"), nil
		}
		if blacklisted {
			log.Printf("[Check] Token blacklisted: %s", jti)
			return denyResponse(typev3.StatusCode_Forbidden, "Token is blacklisted"), nil
		}
	}

	// 4. Allow Request (Inject User ID)
	userID, _ := claims["sub"].(string)
	return allowResponse(userID), nil
}

func allowResponse(userID string) *authv3.CheckResponse {
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
