package jwt

import (
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

func TestNewVerifier_Validation(t *testing.T) {
	tests := []struct {
		name      string
		secretKey string
		algorithm string
		wantErr   bool
	}{
		{
			name:      "Valid params",
			secretKey: "secret",
			algorithm: "HS256",
			wantErr:   false,
		},
		{
			name:      "Empty secretKey",
			secretKey: "",
			algorithm: "HS256",
			wantErr:   true,
		},
		{
			name:      "Whitespace secretKey",
			secretKey: "   ",
			algorithm: "HS256",
			wantErr:   true,
		},
		{
			name:      "Empty algorithm",
			secretKey: "secret",
			algorithm: "",
			wantErr:   true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := NewVerifier(tt.secretKey, tt.algorithm, "", "", time.Minute, "")
			if (err != nil) != tt.wantErr {
				t.Errorf("NewVerifier() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

func TestVerifier_Verify(t *testing.T) {
	secret := "secret"
	issuer := "eco2"
	audience := "eco2-api"
	scope := "read"
	verifier, err := NewVerifier(secret, "HS256", issuer, audience, time.Minute, scope)
	if err != nil {
		t.Fatalf("NewVerifier error: %v", err)
	}

	tests := []struct {
		name    string
		token   string
		wantErr bool
	}{
		{
			name: "Valid Token",
			token: func() string {
				token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
					"sub":   "user123",
					"jti":   "jti123",
					"exp":   time.Now().Add(time.Hour).Unix(),
					"iss":   issuer,
					"aud":   audience,
					"scope": "read write",
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
					"sub":   "user123",
					"jti":   "jti123",
					"exp":   time.Now().Add(-time.Hour).Unix(),
					"iss":   issuer,
					"aud":   audience,
					"scope": scope,
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
		{
			name: "Missing Sub",
			token: func() string {
				token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
					"jti":   "jti123",
					"exp":   time.Now().Add(time.Hour).Unix(),
					"iss":   issuer,
					"aud":   audience,
					"scope": scope,
				})
				s, _ := token.SignedString([]byte(secret))
				return "Bearer " + s
			}(),
			wantErr: true,
		},
		{
			name: "Missing Required Scope",
			token: func() string {
				token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
					"sub":   "user123",
					"jti":   "jti123",
					"exp":   time.Now().Add(time.Hour).Unix(),
					"iss":   issuer,
					"aud":   audience,
					"scope": "write",
				})
				s, _ := token.SignedString([]byte(secret))
				return "Bearer " + s
			}(),
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

func TestVerifier_MissingJTI(t *testing.T) {
	secret := "secret"
	verifier, _ := NewVerifier(secret, "HS256", "", "", time.Minute, "")

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub": "user123",
		"exp": time.Now().Add(time.Hour).Unix(),
	})
	s, _ := token.SignedString([]byte(secret))

	_, err := verifier.Verify(s)
	if err == nil {
		t.Error("Expected error for missing JTI")
	}
}

func TestVerifier_InvalidIssuer(t *testing.T) {
	secret := "secret"
	verifier, _ := NewVerifier(secret, "HS256", "expected-issuer", "", time.Minute, "")

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub": "user123",
		"jti": "jti123",
		"exp": time.Now().Add(time.Hour).Unix(),
		"iss": "wrong-issuer",
	})
	s, _ := token.SignedString([]byte(secret))

	_, err := verifier.Verify(s)
	if err == nil {
		t.Error("Expected error for invalid issuer")
	}
}

func TestVerifier_InvalidAudience(t *testing.T) {
	secret := "secret"
	verifier, _ := NewVerifier(secret, "HS256", "", "expected-audience", time.Minute, "")

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub": "user123",
		"jti": "jti123",
		"exp": time.Now().Add(time.Hour).Unix(),
		"aud": "wrong-audience",
	})
	s, _ := token.SignedString([]byte(secret))

	_, err := verifier.Verify(s)
	if err == nil {
		t.Error("Expected error for invalid audience")
	}
}

func TestVerifier_AudienceAsArray(t *testing.T) {
	secret := "secret"
	verifier, _ := NewVerifier(secret, "HS256", "", "api", time.Minute, "")

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub": "user123",
		"jti": "jti123",
		"exp": time.Now().Add(time.Hour).Unix(),
		"aud": []string{"web", "api", "mobile"},
	})
	s, _ := token.SignedString([]byte(secret))

	_, err := verifier.Verify(s)
	if err != nil {
		t.Errorf("Expected no error for valid audience in array, got: %v", err)
	}
}

func TestVerifier_NoScopeRequired(t *testing.T) {
	secret := "secret"
	verifier, _ := NewVerifier(secret, "HS256", "", "", time.Minute, "")

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub": "user123",
		"jti": "jti123",
		"exp": time.Now().Add(time.Hour).Unix(),
	})
	s, _ := token.SignedString([]byte(secret))

	_, err := verifier.Verify(s)
	if err != nil {
		t.Errorf("Expected no error when no scope required, got: %v", err)
	}
}

func TestScopeContains(t *testing.T) {
	tests := []struct {
		scope    string
		required string
		expected bool
	}{
		{"read write admin", "write", true},
		{"read write admin", "delete", false},
		{"read", "read", true},
		{"", "read", false},
		{"read", "", false},
		{"  read   write  ", "read", true},
	}

	for _, tt := range tests {
		result := scopeContains(tt.scope, tt.required)
		if result != tt.expected {
			t.Errorf("scopeContains(%q, %q): expected %v, got %v",
				tt.scope, tt.required, tt.expected, result)
		}
	}
}

func TestMatchesIssuer(t *testing.T) {
	tests := []struct {
		claims   jwt.MapClaims
		issuer   string
		expected bool
	}{
		{jwt.MapClaims{"iss": "eco2"}, "eco2", true},
		{jwt.MapClaims{"iss": "eco2"}, "other", false},
		{jwt.MapClaims{"iss": "  eco2  "}, "eco2", true},
		{jwt.MapClaims{}, "eco2", false},
		{jwt.MapClaims{"iss": 123}, "eco2", false},
	}

	for _, tt := range tests {
		result := matchesIssuer(tt.claims, tt.issuer)
		if result != tt.expected {
			t.Errorf("matchesIssuer(%v, %q): expected %v, got %v",
				tt.claims, tt.issuer, tt.expected, result)
		}
	}
}

func TestMatchesAudience(t *testing.T) {
	tests := []struct {
		claims   jwt.MapClaims
		audience string
		expected bool
	}{
		{jwt.MapClaims{"aud": "api"}, "api", true},
		{jwt.MapClaims{"aud": "api"}, "web", false},
		{jwt.MapClaims{"aud": []any{"api", "web"}}, "api", true},
		{jwt.MapClaims{"aud": []any{"api", "web"}}, "mobile", false},
		{jwt.MapClaims{"aud": []string{"api", "web"}}, "api", true},
		{jwt.MapClaims{}, "api", false},
		{jwt.MapClaims{"aud": "api"}, "", true}, // Empty audience means no check
	}

	for _, tt := range tests {
		result := matchesAudience(tt.claims, tt.audience)
		if result != tt.expected {
			t.Errorf("matchesAudience(%v, %q): expected %v, got %v",
				tt.claims, tt.audience, tt.expected, result)
		}
	}
}
