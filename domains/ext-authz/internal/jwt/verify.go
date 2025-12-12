package jwt

import (
	"fmt"
	"strings"

	"github.com/golang-jwt/jwt/v5"
)

type Verifier struct {
	secretKey []byte
}

func NewVerifier(secretKey string) *Verifier {
	return &Verifier{
		secretKey: []byte(secretKey),
	}
}

// Verify parses and validates the token. Returns claims if valid.
func (v *Verifier) Verify(tokenString string) (jwt.MapClaims, error) {
	// Remove "Bearer " prefix if present
	tokenString = strings.TrimPrefix(tokenString, "Bearer ")

	token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
		// Validate algorithm
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
		}
		return v.secretKey, nil
	})

	if err != nil {
		return nil, fmt.Errorf("invalid token: %w", err)
	}

	if claims, ok := token.Claims.(jwt.MapClaims); ok && token.Valid {
		return claims, nil
	}

	return nil, fmt.Errorf("invalid token claims")
}
