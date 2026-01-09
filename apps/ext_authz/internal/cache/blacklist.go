// Package cache provides in-memory caching for JWT blacklist.
// This eliminates Redis calls on the hot path, improving latency from ~2ms to <0.01ms.
package cache

import (
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// Metrics for blacklist cache
var (
	cacheSize = promauto.NewGauge(prometheus.GaugeOpts{
		Namespace: "ext_authz",
		Subsystem: "blacklist_cache",
		Name:      "size",
		Help:      "Current number of entries in the blacklist cache",
	})

	cacheHits = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "ext_authz",
		Subsystem: "blacklist_cache",
		Name:      "hits_total",
		Help:      "Total number of cache hits (blacklisted tokens found)",
	})

	cacheMisses = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "ext_authz",
		Subsystem: "blacklist_cache",
		Name:      "misses_total",
		Help:      "Total number of cache misses (tokens not in blacklist)",
	})

	cacheEvictions = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "ext_authz",
		Subsystem: "blacklist_cache",
		Name:      "evictions_total",
		Help:      "Total number of expired entries evicted from cache",
	})

	cacheAdditions = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "ext_authz",
		Subsystem: "blacklist_cache",
		Name:      "additions_total",
		Help:      "Total number of entries added to cache",
	})

	lookupDuration = promauto.NewHistogram(prometheus.HistogramOpts{
		Namespace: "ext_authz",
		Subsystem: "blacklist_cache",
		Name:      "lookup_duration_seconds",
		Help:      "Time spent looking up entries in the cache",
		Buckets:   prometheus.ExponentialBucketsRange(0.000001, 0.001, 8), // 1µs to 1ms
	})
)

// BlacklistCache is an in-memory cache for blacklisted JWT tokens.
// It uses sync.Map for thread-safe O(1) lookups and stores TTL per entry.
type BlacklistCache struct {
	items    sync.Map      // map[string]time.Time (jti → expireAt)
	ttlCheck time.Duration // cleanup interval
	done     chan struct{} // shutdown signal
}

// NewBlacklistCache creates a new BlacklistCache with a background cleanup goroutine.
// cleanupInterval determines how often expired entries are removed.
func NewBlacklistCache(cleanupInterval time.Duration) *BlacklistCache {
	c := &BlacklistCache{
		ttlCheck: cleanupInterval,
		done:     make(chan struct{}),
	}
	go c.cleanupLoop()
	return c
}

// IsBlacklisted checks if a JTI is in the blacklist.
// Returns true if the token is blacklisted and not expired.
// This is O(1) and does not involve any network I/O.
func (c *BlacklistCache) IsBlacklisted(jti string) bool {
	start := time.Now()
	defer func() {
		lookupDuration.Observe(time.Since(start).Seconds())
	}()

	val, ok := c.items.Load(jti)
	if !ok {
		cacheMisses.Inc()
		return false
	}

	// Safe type assertion to prevent panic
	expireAt, ok := val.(time.Time)
	if !ok {
		// Invalid type stored - delete and treat as miss
		c.items.Delete(jti)
		cacheMisses.Inc()
		return false
	}

	if time.Now().After(expireAt) {
		// Lazy deletion of expired entry
		c.items.Delete(jti)
		cacheEvictions.Inc()
		c.updateSizeMetric()
		cacheMisses.Inc()
		return false
	}

	cacheHits.Inc()
	return true
}

// Add adds a JTI to the blacklist with an expiration time.
// If the JTI already exists, it will be overwritten.
func (c *BlacklistCache) Add(jti string, expireAt time.Time) {
	c.items.Store(jti, expireAt)
	cacheAdditions.Inc()
	c.updateSizeMetric()
}

// LoadBulk loads multiple entries at once (used during bootstrap).
func (c *BlacklistCache) LoadBulk(items map[string]time.Time) int {
	count := 0
	for jti, exp := range items {
		c.items.Store(jti, exp)
		count++
	}
	cacheAdditions.Add(float64(count))
	c.updateSizeMetric()
	return count
}

// Size returns the current number of entries in the cache.
func (c *BlacklistCache) Size() int {
	count := 0
	c.items.Range(func(_, _ any) bool {
		count++
		return true
	})
	return count
}

// Stop stops the background cleanup goroutine.
func (c *BlacklistCache) Stop() {
	close(c.done)
}

// cleanupLoop periodically removes expired entries from the cache.
func (c *BlacklistCache) cleanupLoop() {
	ticker := time.NewTicker(c.ttlCheck)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			c.cleanup()
		case <-c.done:
			return
		}
	}
}

// cleanup removes all expired entries from the cache.
func (c *BlacklistCache) cleanup() {
	now := time.Now()
	evicted := 0

	c.items.Range(func(key, value any) bool {
		// Safe type assertion
		expireAt, ok := value.(time.Time)
		if !ok {
			// Invalid type - delete entry
			c.items.Delete(key)
			evicted++
			return true
		}
		if now.After(expireAt) {
			c.items.Delete(key)
			evicted++
		}
		return true
	})

	if evicted > 0 {
		cacheEvictions.Add(float64(evicted))
		c.updateSizeMetric()
	}
}

// updateSizeMetric updates the cache size gauge.
func (c *BlacklistCache) updateSizeMetric() {
	cacheSize.Set(float64(c.Size()))
}
