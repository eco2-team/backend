package jwt

import (
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

// Token prefix
const (
	BearerPrefix = "Bearer "
)

// JWT claim keys (exported for use by other packages)
const (
	ClaimSub      = "sub"
	ClaimJTI      = "jti"
	ClaimIss      = "iss"
	ClaimAud      = "aud"
	ClaimScope    = "scope"
	ClaimProvider = "provider"
)

type Verifier struct {
	secretKey []byte
	algorithm string
	issuer    string
	audience  string
	clockSkew time.Duration
	reqScope  string
}

func NewVerifier(secretKey, algorithm, issuer, audience string, clockSkew time.Duration, requiredScope string) (*Verifier, error) {
	if strings.TrimSpace(secretKey) == "" {
		return nil, errors.New("secretKey is required")
	}
	if strings.TrimSpace(algorithm) == "" {
		return nil, errors.New("algorithm is required")
	}
	return &Verifier{
		secretKey: []byte(secretKey),
		algorithm: algorithm,
		issuer:    issuer,
		audience:  audience,
		clockSkew: clockSkew,
		reqScope:  strings.TrimSpace(requiredScope),
	}, nil
}

// Claims is the return type for Verify, compatible with server.TokenVerifier interface.
type Claims = map[string]any

// Verify parses and validates the token. Returns claims if valid.
func (v *Verifier) Verify(tokenString string) (Claims, error) {
	// Remove "Bearer " prefix if present
	tokenString = strings.TrimPrefix(tokenString, BearerPrefix)

	parser := jwt.NewParser(
		jwt.WithValidMethods([]string{v.algorithm}),
		jwt.WithLeeway(v.clockSkew),
	)

	claims := jwt.MapClaims{}
	token, err := parser.ParseWithClaims(tokenString, claims, func(token *jwt.Token) (interface{}, error) {
		return v.secretKey, nil
	})

	if err != nil {
		return nil, fmt.Errorf("invalid token: %w", err)
	}

	if !token.Valid {
		return nil, errors.New("invalid token claims")
	}

	// Required claims
	sub, ok := claims[ClaimSub].(string)
	if !ok || strings.TrimSpace(sub) == "" {
		return nil, errors.New("missing required claim: sub")
	}

	jti, ok := claims[ClaimJTI].(string)
	if !ok || strings.TrimSpace(jti) == "" {
		return nil, errors.New("missing required claim: jti")
	}

	// exp/nbf/iat checked by parser; issuer/audience optional
	if v.issuer != "" && !matchesIssuer(claims, v.issuer) {
		return nil, fmt.Errorf("invalid issuer: %v", claims[ClaimIss])
	}
	if v.audience != "" && !matchesAudience(claims, v.audience) {
		return nil, fmt.Errorf("invalid audience: %v", claims[ClaimAud])
	}

	if v.reqScope != "" {
		scope, _ := claims[ClaimScope].(string)
		if !scopeContains(scope, v.reqScope) {
			return nil, fmt.Errorf("required scope missing: %s", v.reqScope)
		}
	}

	return Claims(claims), nil
}

func scopeContains(scope string, required string) bool {
	if scope == "" || required == "" {
		return false
	}
	parts := strings.Fields(scope)
	for _, p := range parts {
		if p == required {
			return true
		}
	}
	return false
}

func matchesIssuer(claims jwt.MapClaims, issuer string) bool {
	iss, ok := claims[ClaimIss].(string)
	if !ok {
		return false
	}
	return strings.TrimSpace(iss) == issuer
}

func matchesAudience(claims jwt.MapClaims, audience string) bool {
	if audience == "" {
		return true
	}
	switch aud := claims[ClaimAud].(type) {
	case string:
		return aud == audience
	case []any:
		for _, a := range aud {
			if s, ok := a.(string); ok && s == audience {
				return true
			}
		}
	case []string:
		for _, s := range aud {
			if s == audience {
				return true
			}
		}
	}
	return false
}
