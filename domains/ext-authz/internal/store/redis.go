package store

import (
	"context"
	"fmt"

	"github.com/redis/go-redis/v9"
)

const blacklistKeyPrefix = "blacklist:"

// RedisClient는 Store가 의존하는 최소 인터페이스다.
type RedisClient interface {
	Exists(ctx context.Context, keys ...string) *redis.IntCmd
	Ping(ctx context.Context) *redis.StatusCmd
	Close() error
}

var _ RedisClient = (*redis.Client)(nil)

type Store struct {
	client RedisClient
}

func New(ctx context.Context, redisURL string) (*Store, error) {
	opts, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf("failed to parse redis url: %w", err)
	}

	client := redis.NewClient(opts)

	if err := client.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("failed to connect to redis: %w", err)
	}

	return &Store{client: client}, nil
}

func NewWithClient(client RedisClient) (*Store, error) {
	if client == nil {
		return nil, fmt.Errorf("redis client is nil")
	}
	return &Store{client: client}, nil
}

func (s *Store) Close() error {
	if s == nil || s.client == nil {
		return nil
	}
	return s.client.Close()
}

// IsBlacklisted checks if the given JTI (JWT ID) exists in the blacklist.
// Key format matches Python backend: "blacklist:{jti}"
func (s *Store) IsBlacklisted(ctx context.Context, jti string) (bool, error) {
	key := blacklistKey(jti)
	exists, err := s.client.Exists(ctx, key).Result()
	if err != nil {
		return false, fmt.Errorf("redis error: %w", err)
	}
	return exists > 0, nil
}

func blacklistKey(jti string) string {
	return blacklistKeyPrefix + jti
}
