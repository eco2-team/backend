package jwt

import (
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

func TestVerifier_Verify(t *testing.T) {
	secret := "secret"
	verifier := NewVerifier(secret)

	tests := []struct {
		name    string
		token   string
		wantErr bool
	}{
		{
			name: "Valid Token",
			token: func() string {
				token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
					"sub": "user123",
					"jti": "jti123",
					"exp": time.Now().Add(time.Hour).Unix(),
				})
				s, _ := token.SignedString([]byte(secret))
				return "Bearer " + s
			}(),
			wantErr: false,
		},
		{
			name: "Expired Token",
			token: func() string {
				token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
					"sub": "user123",
					"exp": time.Now().Add(-time.Hour).Unix(),
				})
				s, _ := token.SignedString([]byte(secret))
				return "Bearer " + s
			}(),
			wantErr: true,
		},
		{
			name:    "Invalid Signature",
			token:   "Bearer " + "invalid.token.string",
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := verifier.Verify(tt.token)
			if (err != nil) != tt.wantErr {
				t.Errorf("Verifier.Verify() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}
