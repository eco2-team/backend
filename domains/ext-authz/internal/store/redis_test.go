package store

import (
	"context"
	"errors"
	"testing"

	"github.com/redis/go-redis/v9"
)

type fakeRedisClient struct {
	existsReturn   *redis.IntCmd
	pingReturn     *redis.StatusCmd
	closeErr       error
	lastExistsKeys []string
}

func (f *fakeRedisClient) Exists(ctx context.Context, keys ...string) *redis.IntCmd {
	f.lastExistsKeys = keys
	return f.existsReturn
}

func (f *fakeRedisClient) Ping(ctx context.Context) *redis.StatusCmd {
	if f.pingReturn != nil {
		return f.pingReturn
	}
	return redis.NewStatusResult("PONG", nil)
}

func (f *fakeRedisClient) Close() error {
	return f.closeErr
}

func TestNewWithClientNil(t *testing.T) {
	if _, err := NewWithClient(nil); err == nil {
		t.Fatalf("expected error when client is nil")
	}
}

func TestIsBlacklistedTrue(t *testing.T) {
	client := &fakeRedisClient{
		existsReturn: redis.NewIntResult(1, nil),
	}

	s, err := NewWithClient(client)
	if err != nil {
		t.Fatalf("NewWithClient error: %v", err)
	}

	blacklisted, err := s.IsBlacklisted(context.Background(), "abc")
	if err != nil {
		t.Fatalf("IsBlacklisted returned error: %v", err)
	}
	if !blacklisted {
		t.Fatalf("expected blacklisted to be true")
	}
	if len(client.lastExistsKeys) != 1 || client.lastExistsKeys[0] != "blacklist:abc" {
		t.Fatalf("unexpected keys passed to Exists: %v", client.lastExistsKeys)
	}
}

func TestIsBlacklistedFalse(t *testing.T) {
	client := &fakeRedisClient{
		existsReturn: redis.NewIntResult(0, nil),
	}

	s, err := NewWithClient(client)
	if err != nil {
		t.Fatalf("NewWithClient error: %v", err)
	}

	blacklisted, err := s.IsBlacklisted(context.Background(), "def")
	if err != nil {
		t.Fatalf("IsBlacklisted returned error: %v", err)
	}
	if blacklisted {
		t.Fatalf("expected blacklisted to be false")
	}
}

func TestIsBlacklistedRedisError(t *testing.T) {
	client := &fakeRedisClient{
		existsReturn: redis.NewIntResult(0, errors.New("boom")),
	}

	s, err := NewWithClient(client)
	if err != nil {
		t.Fatalf("NewWithClient error: %v", err)
	}

	if _, err := s.IsBlacklisted(context.Background(), "ghi"); err == nil {
		t.Fatalf("expected error from IsBlacklisted")
	}
}

func TestClose(t *testing.T) {
	client := &fakeRedisClient{
		closeErr: nil,
	}

	s, err := NewWithClient(client)
	if err != nil {
		t.Fatalf("NewWithClient error: %v", err)
	}

	if err := s.Close(); err != nil {
		t.Fatalf("Close returned error: %v", err)
	}
}

func TestCloseError(t *testing.T) {
	client := &fakeRedisClient{
		closeErr: errors.New("close error"),
	}

	s, err := NewWithClient(client)
	if err != nil {
		t.Fatalf("NewWithClient error: %v", err)
	}

	if err := s.Close(); err == nil {
		t.Fatalf("expected error from Close")
	}
}

func TestCloseNilStore(t *testing.T) {
	var s *Store
	if err := s.Close(); err == nil {
		t.Fatalf("expected error when store is nil")
	}
}

func TestCloseNilClient(t *testing.T) {
	s := &Store{client: nil}
	if err := s.Close(); err == nil {
		t.Fatalf("expected error when client is nil")
	}
}

func TestBlacklistKey(t *testing.T) {
	tests := []struct {
		jti      string
		expected string
	}{
		{"abc", "blacklist:abc"},
		{"test-jti-123", "blacklist:test-jti-123"},
		{"", "blacklist:"},
	}

	for _, tt := range tests {
		result := blacklistKey(tt.jti)
		if result != tt.expected {
			t.Errorf("blacklistKey(%s): expected %s, got %s", tt.jti, tt.expected, result)
		}
	}
}
