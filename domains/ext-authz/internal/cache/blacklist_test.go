package cache

import (
	"fmt"
	"sync"
	"testing"
	"time"
)

func TestBlacklistCache_IsBlacklisted(t *testing.T) {
	cache := NewBlacklistCache(1 * time.Minute)
	defer cache.Stop()

	jti := "test-jti-123"

	// Initially not blacklisted
	if cache.IsBlacklisted(jti) {
		t.Error("Expected JTI to not be blacklisted initially")
	}

	// Add to blacklist
	cache.Add(jti, time.Now().Add(1*time.Hour))

	// Now should be blacklisted
	if !cache.IsBlacklisted(jti) {
		t.Error("Expected JTI to be blacklisted after Add")
	}
}

func TestBlacklistCache_ExpiredEntry(t *testing.T) {
	cache := NewBlacklistCache(1 * time.Minute)
	defer cache.Stop()

	jti := "expired-jti"

	// Add with past expiration
	cache.Add(jti, time.Now().Add(-1*time.Second))

	// Should not be blacklisted (expired)
	if cache.IsBlacklisted(jti) {
		t.Error("Expected expired JTI to not be blacklisted")
	}

	// After lazy deletion, size should be 0
	if cache.Size() != 0 {
		t.Errorf("Expected size 0 after lazy deletion, got %d", cache.Size())
	}
}

func TestBlacklistCache_LoadBulk(t *testing.T) {
	cache := NewBlacklistCache(1 * time.Minute)
	defer cache.Stop()

	items := map[string]time.Time{
		"jti-1": time.Now().Add(1 * time.Hour),
		"jti-2": time.Now().Add(2 * time.Hour),
		"jti-3": time.Now().Add(3 * time.Hour),
	}

	loaded := cache.LoadBulk(items)
	if loaded != 3 {
		t.Errorf("Expected 3 loaded, got %d", loaded)
	}

	if cache.Size() != 3 {
		t.Errorf("Expected size 3, got %d", cache.Size())
	}

	for jti := range items {
		if !cache.IsBlacklisted(jti) {
			t.Errorf("Expected %s to be blacklisted", jti)
		}
	}
}

func TestBlacklistCache_Size(t *testing.T) {
	cache := NewBlacklistCache(1 * time.Minute)
	defer cache.Stop()

	if cache.Size() != 0 {
		t.Error("Expected initial size to be 0")
	}

	cache.Add("jti-1", time.Now().Add(1*time.Hour))
	cache.Add("jti-2", time.Now().Add(1*time.Hour))

	if cache.Size() != 2 {
		t.Errorf("Expected size 2, got %d", cache.Size())
	}
}

func TestBlacklistCache_Stop(t *testing.T) {
	cache := NewBlacklistCache(100 * time.Millisecond)

	// Add some entries
	cache.Add("jti-1", time.Now().Add(1*time.Hour))
	cache.Add("jti-2", time.Now().Add(1*time.Hour))

	// Stop should not panic
	cache.Stop()

	// Cache should still be queryable after stop
	if !cache.IsBlacklisted("jti-1") {
		t.Error("Expected jti-1 to still be blacklisted after Stop")
	}
}

func TestBlacklistCache_Cleanup(t *testing.T) {
	// Create cache with very short cleanup interval
	cache := NewBlacklistCache(50 * time.Millisecond)
	defer cache.Stop()

	// Add entry that expires in 100ms
	cache.Add("short-lived", time.Now().Add(100*time.Millisecond))
	cache.Add("long-lived", time.Now().Add(1*time.Hour))

	// Verify initial state
	if cache.Size() != 2 {
		t.Errorf("Expected size 2, got %d", cache.Size())
	}

	// Wait for entry to expire and cleanup to run
	time.Sleep(200 * time.Millisecond)

	// Short-lived should be cleaned up
	if cache.IsBlacklisted("short-lived") {
		t.Error("Expected short-lived to be expired")
	}

	// Long-lived should still exist
	if !cache.IsBlacklisted("long-lived") {
		t.Error("Expected long-lived to still be blacklisted")
	}

	// Size should be 1
	if cache.Size() != 1 {
		t.Errorf("Expected size 1 after cleanup, got %d", cache.Size())
	}
}

func TestBlacklistCache_ConcurrentAccess(t *testing.T) {
	cache := NewBlacklistCache(1 * time.Minute)
	defer cache.Stop()

	const numGoroutines = 100
	const numOperations = 1000

	var wg sync.WaitGroup
	wg.Add(numGoroutines)

	for i := 0; i < numGoroutines; i++ {
		go func(id int) {
			defer wg.Done()
			for j := 0; j < numOperations; j++ {
				jti := fmt.Sprintf("jti-%d-%d", id, j)
				cache.Add(jti, time.Now().Add(1*time.Hour))
				cache.IsBlacklisted(jti)
			}
		}(i)
	}

	wg.Wait()

	// Should have exactly numGoroutines * numOperations entries
	expectedSize := numGoroutines * numOperations
	if cache.Size() != expectedSize {
		t.Errorf("Expected size %d, got %d", expectedSize, cache.Size())
	}
}

func TestBlacklistCache_Overwrite(t *testing.T) {
	cache := NewBlacklistCache(1 * time.Minute)
	defer cache.Stop()

	jti := "overwrite-jti"

	// Add with short expiration
	cache.Add(jti, time.Now().Add(100*time.Millisecond))

	// Overwrite with longer expiration
	cache.Add(jti, time.Now().Add(1*time.Hour))

	// Wait for original to expire
	time.Sleep(150 * time.Millisecond)

	// Should still be blacklisted (overwritten with longer TTL)
	if !cache.IsBlacklisted(jti) {
		t.Error("Expected jti to still be blacklisted after overwrite")
	}

	// Size should be 1 (not 2)
	if cache.Size() != 1 {
		t.Errorf("Expected size 1, got %d", cache.Size())
	}
}

func TestBlacklistCache_EmptyJTI(t *testing.T) {
	cache := NewBlacklistCache(1 * time.Minute)
	defer cache.Stop()

	// Add empty JTI (should work but not recommended)
	cache.Add("", time.Now().Add(1*time.Hour))

	// Check empty JTI
	if !cache.IsBlacklisted("") {
		t.Error("Expected empty JTI to be blacklisted")
	}
}

func BenchmarkIsBlacklisted(b *testing.B) {
	cache := NewBlacklistCache(1 * time.Minute)
	defer cache.Stop()

	// Pre-populate with 10000 entries
	for i := 0; i < 10000; i++ {
		cache.Add(fmt.Sprintf("jti-%d", i), time.Now().Add(1*time.Hour))
	}

	jti := "jti-5000" // existing entry

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		cache.IsBlacklisted(jti)
	}
}

func BenchmarkIsBlacklisted_Miss(b *testing.B) {
	cache := NewBlacklistCache(1 * time.Minute)
	defer cache.Stop()

	// Pre-populate with 10000 entries
	for i := 0; i < 10000; i++ {
		cache.Add(fmt.Sprintf("jti-%d", i), time.Now().Add(1*time.Hour))
	}

	jti := "non-existent-jti" // miss case

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		cache.IsBlacklisted(jti)
	}
}

func BenchmarkAdd(b *testing.B) {
	cache := NewBlacklistCache(1 * time.Minute)
	defer cache.Stop()

	expireAt := time.Now().Add(1 * time.Hour)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		cache.Add(fmt.Sprintf("jti-%d", i), expireAt)
	}
}

func BenchmarkConcurrentIsBlacklisted(b *testing.B) {
	cache := NewBlacklistCache(1 * time.Minute)
	defer cache.Stop()

	// Pre-populate
	for i := 0; i < 10000; i++ {
		cache.Add(fmt.Sprintf("jti-%d", i), time.Now().Add(1*time.Hour))
	}

	b.ResetTimer()
	b.RunParallel(func(pb *testing.PB) {
		i := 0
		for pb.Next() {
			cache.IsBlacklisted(fmt.Sprintf("jti-%d", i%10000))
			i++
		}
	})
}

func TestBlacklistCache_InvalidTypeInMap(t *testing.T) {
	cache := NewBlacklistCache(1 * time.Minute)
	defer cache.Stop()

	jti := "invalid-type-jti"

	// Directly store an invalid type (not time.Time)
	cache.items.Store(jti, "invalid-string-value")

	// IsBlacklisted should handle invalid type gracefully
	if cache.IsBlacklisted(jti) {
		t.Error("Expected IsBlacklisted to return false for invalid type")
	}

	// Entry should be deleted after invalid type detection
	_, exists := cache.items.Load(jti)
	if exists {
		t.Error("Expected invalid type entry to be deleted")
	}
}

func TestBlacklistCache_CleanupInvalidType(t *testing.T) {
	cache := NewBlacklistCache(1 * time.Minute)
	defer cache.Stop()

	// Store invalid types directly
	cache.items.Store("invalid-1", 12345)                   // int
	cache.items.Store("invalid-2", "string-value")          // string
	cache.items.Store("valid", time.Now().Add(1*time.Hour)) // valid

	// Run cleanup
	cache.cleanup()

	// Invalid entries should be removed
	if _, exists := cache.items.Load("invalid-1"); exists {
		t.Error("Expected invalid-1 to be cleaned up")
	}
	if _, exists := cache.items.Load("invalid-2"); exists {
		t.Error("Expected invalid-2 to be cleaned up")
	}

	// Valid entry should remain
	if _, exists := cache.items.Load("valid"); !exists {
		t.Error("Expected valid entry to remain")
	}
}
