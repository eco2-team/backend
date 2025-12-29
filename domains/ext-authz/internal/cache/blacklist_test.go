package cache

import (
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

func BenchmarkIsBlacklisted(b *testing.B) {
	cache := NewBlacklistCache(1 * time.Minute)
	defer cache.Stop()

	// Pre-populate with 10000 entries
	for i := 0; i < 10000; i++ {
		cache.Add("jti-"+string(rune(i)), time.Now().Add(1*time.Hour))
	}

	jti := "jti-5000" // existing entry

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		cache.IsBlacklisted(jti)
	}
}
