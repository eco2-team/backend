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
