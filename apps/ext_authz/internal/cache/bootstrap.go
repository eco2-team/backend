package cache

import (
	"context"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"

	"github.com/eco2-team/backend/domains/ext-authz/internal/logging"
)

const (
	// blacklistKeyPrefix is the prefix for blacklist keys in Redis.
	blacklistKeyPrefix = "blacklist:"
	// scanBatchSize is the number of keys to scan per iteration.
	scanBatchSize = 1000
)

// BootstrapFromRedis loads all blacklisted JTIs from Redis into memory.
// This is called once at startup to warm up the cache.
// Returns a map of JTI → expireAt.
func BootstrapFromRedis(ctx context.Context, client *redis.Client, logger *logging.Logger) (map[string]time.Time, error) {
	items := make(map[string]time.Time)
	var cursor uint64
	pattern := blacklistKeyPrefix + "*"

	startTime := time.Now()
	totalScanned := 0

	for {
		keys, nextCursor, err := client.Scan(ctx, cursor, pattern, scanBatchSize).Result()
		if err != nil {
			logger.Error("Redis SCAN failed during bootstrap",
				"error", err,
				"cursor", cursor,
				"scanned_so_far", totalScanned,
			)
			return nil, err
		}

		totalScanned += len(keys)

		// Get TTL for each key and calculate expireAt
		for _, key := range keys {
			jti := strings.TrimPrefix(key, blacklistKeyPrefix)

			ttl, err := client.TTL(ctx, key).Result()
			if err != nil {
				logger.Warn("Failed to get TTL for key",
					"key", key,
					"error", err,
				)
				continue
			}

			// Skip if already expired or no TTL set
			if ttl <= 0 {
				continue
			}

			expireAt := time.Now().Add(ttl)
			items[jti] = expireAt
		}

		cursor = nextCursor
		if cursor == 0 {
			break
		}
	}

	elapsed := time.Since(startTime)
	logger.Info("Bootstrap completed",
		"loaded_entries", len(items),
		"total_scanned", totalScanned,
		"elapsed_ms", elapsed.Milliseconds(),
	)

	return items, nil
}
