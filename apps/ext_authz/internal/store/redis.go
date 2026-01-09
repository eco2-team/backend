package store

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"

	"github.com/eco2-team/backend/domains/ext-authz/internal/constants"
)

const blacklistKeyPrefix = "blacklist:"

// RedisClient는 Store가 의존하는 최소 인터페이스다.
type RedisClient interface {
	Exists(ctx context.Context, keys ...string) *redis.IntCmd
	Ping(ctx context.Context) *redis.StatusCmd
	Close() error
}

var _ RedisClient = (*redis.Client)(nil)

// PoolOptions contains Redis connection pool settings.
type PoolOptions struct {
	PoolSize     int           // Maximum number of connections
	MinIdleConns int           // Minimum idle connections to maintain
	PoolTimeout  time.Duration // Time to wait for a connection from the pool
	ReadTimeout  time.Duration // Timeout for read operations
	WriteTimeout time.Duration // Timeout for write operations
}

type Store struct {
	client RedisClient
}

// New creates a new Store with the given Redis URL and pool options.
func New(ctx context.Context, redisURL string, poolOpts *PoolOptions) (*Store, error) {
	if poolOpts == nil {
		return nil, fmt.Errorf(constants.ErrPoolOptionsRequired)
	}

	opts, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf(constants.ErrRedisURLParse, err)
	}

	// Apply pool options
	opts.PoolSize = poolOpts.PoolSize
	opts.MinIdleConns = poolOpts.MinIdleConns
	opts.PoolTimeout = poolOpts.PoolTimeout
	opts.ReadTimeout = poolOpts.ReadTimeout
	opts.WriteTimeout = poolOpts.WriteTimeout

	client := redis.NewClient(opts)

	if err := client.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf(constants.ErrRedisConnect, err)
	}

	return &Store{client: client}, nil
}

func NewWithClient(client RedisClient) (*Store, error) {
	if client == nil {
		return nil, fmt.Errorf(constants.ErrRedisClientNil)
	}
	return &Store{client: client}, nil
}

func (s *Store) Close() error {
	if s == nil {
		return errors.New(constants.ErrStoreNil)
	}
	if s.client == nil {
		return errors.New(constants.ErrRedisClientNil)
	}
	return s.client.Close()
}

func (s *Store) IsBlacklisted(ctx context.Context, jti string) (bool, error) {
	key := blacklistKey(jti)
	exists, err := s.client.Exists(ctx, key).Result()
	if err != nil {
		return false, fmt.Errorf(constants.ErrRedisOperation, err)
	}
	return exists > 0, nil
}

func blacklistKey(jti string) string {
	return blacklistKeyPrefix + jti
}
