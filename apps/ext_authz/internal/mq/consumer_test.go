package mq

import (
	"encoding/json"
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/eco2-team/backend/domains/ext-authz/internal/cache"
	"github.com/eco2-team/backend/domains/ext-authz/internal/logging"
)

func TestBlacklistEvent_JSONParsing(t *testing.T) {
	tests := []struct {
		name     string
		json     string
		expected BlacklistEvent
		wantErr  bool
	}{
		{
			name: "valid add event",
			json: `{"type":"add","jti":"test-jti-123","expires_at":"2025-12-30T12:00:00Z"}`,
			expected: BlacklistEvent{
				Type:     "add",
				JTI:      "test-jti-123",
				ExpireAt: time.Date(2025, 12, 30, 12, 0, 0, 0, time.UTC),
			},
			wantErr: false,
		},
		{
			name: "valid remove event",
			json: `{"type":"remove","jti":"test-jti-456"}`,
			expected: BlacklistEvent{
				Type: "remove",
				JTI:  "test-jti-456",
			},
			wantErr: false,
		},
		{
			name:    "invalid json",
			json:    `{invalid`,
			wantErr: true,
		},
		{
			name: "empty jti",
			json: `{"type":"add","jti":"","expires_at":"2025-12-30T12:00:00Z"}`,
			expected: BlacklistEvent{
				Type:     "add",
				JTI:      "",
				ExpireAt: time.Date(2025, 12, 30, 12, 0, 0, 0, time.UTC),
			},
			wantErr: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var event BlacklistEvent
			err := json.Unmarshal([]byte(tt.json), &event)

			if tt.wantErr {
				if err == nil {
					t.Errorf("Expected error, got nil")
				}
				return
			}

			if err != nil {
				t.Errorf("Unexpected error: %v", err)
				return
			}

			if event.Type != tt.expected.Type {
				t.Errorf("Type: expected %s, got %s", tt.expected.Type, event.Type)
			}
			if event.JTI != tt.expected.JTI {
				t.Errorf("JTI: expected %s, got %s", tt.expected.JTI, event.JTI)
			}
			if !tt.expected.ExpireAt.IsZero() && !event.ExpireAt.Equal(tt.expected.ExpireAt) {
				t.Errorf("ExpireAt: expected %v, got %v", tt.expected.ExpireAt, event.ExpireAt)
			}
		})
	}
}

func TestBlacklistConsumer_HandleMessage(t *testing.T) {
	blacklistCache := cache.NewBlacklistCache(1 * time.Minute)
	defer blacklistCache.Stop()

	logger := logging.NewTestLogger()
	consumer := NewBlacklistConsumer("amqp://localhost:5672", blacklistCache, logger)

	tests := []struct {
		name            string
		message         []byte
		expectedInCache bool
		jti             string
	}{
		{
			name:            "valid add event",
			message:         []byte(`{"type":"add","jti":"valid-jti","expires_at":"2099-12-30T12:00:00Z"}`),
			expectedInCache: true,
			jti:             "valid-jti",
		},
		{
			name:            "expired add event",
			message:         []byte(`{"type":"add","jti":"expired-jti","expires_at":"2020-01-01T00:00:00Z"}`),
			expectedInCache: false,
			jti:             "expired-jti",
		},
		{
			name:            "remove event (ignored)",
			message:         []byte(`{"type":"remove","jti":"remove-jti"}`),
			expectedInCache: false,
			jti:             "remove-jti",
		},
		{
			name:            "unknown event type",
			message:         []byte(`{"type":"unknown","jti":"unknown-jti"}`),
			expectedInCache: false,
			jti:             "unknown-jti",
		},
		{
			name:            "invalid json",
			message:         []byte(`{invalid`),
			expectedInCache: false,
			jti:             "",
		},
		{
			name:            "empty jti add event",
			message:         []byte(`{"type":"add","jti":"","expires_at":"2099-12-30T12:00:00Z"}`),
			expectedInCache: false,
			jti:             "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			consumer.handleMessage(tt.message)

			if tt.jti != "" {
				isBlacklisted := blacklistCache.IsBlacklisted(tt.jti)
				if isBlacklisted != tt.expectedInCache {
					t.Errorf("IsBlacklisted(%s): expected %v, got %v",
						tt.jti, tt.expectedInCache, isBlacklisted)
				}
			}
		})
	}
}

func TestNewBlacklistConsumer(t *testing.T) {
	blacklistCache := cache.NewBlacklistCache(1 * time.Minute)
	defer blacklistCache.Stop()

	logger := logging.NewTestLogger()

	consumer := NewBlacklistConsumer("amqp://localhost:5672", blacklistCache, logger)

	if consumer == nil {
		t.Error("Expected consumer to be created")
	}

	if consumer.amqpURL != "amqp://localhost:5672" {
		t.Errorf("Expected amqpURL to be 'amqp://localhost:5672', got '%s'", consumer.amqpURL)
	}

	if consumer.cache != blacklistCache {
		t.Error("Expected cache to be set correctly")
	}
}

func TestBlacklistConsumer_Stop(t *testing.T) {
	blacklistCache := cache.NewBlacklistCache(1 * time.Minute)
	defer blacklistCache.Stop()

	logger := logging.NewTestLogger()
	consumer := NewBlacklistConsumer("amqp://localhost:5672", blacklistCache, logger)

	// Stop should not panic even without Start
	consumer.Stop()

	// Verify done channel is closed
	select {
	case <-consumer.done:
		// Expected
	default:
		t.Error("Expected done channel to be closed")
	}
}

func TestBlacklistConsumer_Start(t *testing.T) {
	blacklistCache := cache.NewBlacklistCache(1 * time.Minute)
	defer blacklistCache.Stop()

	logger := logging.NewTestLogger()
	consumer := NewBlacklistConsumer("amqp://invalid-url", blacklistCache, logger)

	// Start should not block
	consumer.Start()

	// Give some time for goroutine to start
	time.Sleep(10 * time.Millisecond)

	// Stop should work after Start
	consumer.Stop()

	// Verify done channel is closed
	select {
	case <-consumer.done:
		// Expected
	case <-time.After(100 * time.Millisecond):
		t.Error("Expected done channel to be closed")
	}
}

func TestBlacklistConsumer_StartAndStop(t *testing.T) {
	blacklistCache := cache.NewBlacklistCache(1 * time.Minute)
	defer blacklistCache.Stop()

	logger := logging.NewTestLogger()
	consumer := NewBlacklistConsumer("amqp://localhost:5672", blacklistCache, logger)

	// Multiple start/stop cycles should not panic
	consumer.Start()
	time.Sleep(10 * time.Millisecond)
	consumer.Stop()

	// Verify graceful shutdown
	select {
	case <-consumer.done:
		// Expected
	case <-time.After(100 * time.Millisecond):
		t.Error("Expected consumer to stop gracefully")
	}
}

func TestBlacklistConsumer_HandleMessage_AllBranches(t *testing.T) {
	blacklistCache := cache.NewBlacklistCache(1 * time.Minute)
	defer blacklistCache.Stop()

	logger := logging.NewTestLogger()
	consumer := NewBlacklistConsumer("amqp://localhost:5672", blacklistCache, logger)

	// Test all message type branches
	testCases := []struct {
		name        string
		message     []byte
		expectCache bool
		jti         string
	}{
		// Valid add with future expiry
		{
			name:        "add_future_expiry",
			message:     []byte(`{"type":"add","jti":"future-jti","expires_at":"2099-12-31T23:59:59Z"}`),
			expectCache: true,
			jti:         "future-jti",
		},
		// Valid add with very long JTI
		{
			name:        "add_long_jti",
			message:     []byte(`{"type":"add","jti":"very-long-jti-identifier-that-is-used-for-testing-purposes-12345","expires_at":"2099-12-30T12:00:00Z"}`),
			expectCache: true,
			jti:         "very-long-jti-identifier-that-is-used-for-testing-purposes-12345",
		},
		// Remove event (processed but doesn't affect cache)
		{
			name:        "remove_event",
			message:     []byte(`{"type":"remove","jti":"remove-test-jti"}`),
			expectCache: false,
			jti:         "remove-test-jti",
		},
		// Unknown type
		{
			name:        "unknown_type",
			message:     []byte(`{"type":"delete","jti":"delete-jti"}`),
			expectCache: false,
			jti:         "delete-jti",
		},
		// Empty type
		{
			name:        "empty_type",
			message:     []byte(`{"type":"","jti":"empty-type-jti"}`),
			expectCache: false,
			jti:         "empty-type-jti",
		},
		// Malformed JSON
		{
			name:        "malformed_json",
			message:     []byte(`{"type":"add","jti":"malformed`),
			expectCache: false,
			jti:         "",
		},
		// Empty body
		{
			name:        "empty_body",
			message:     []byte(``),
			expectCache: false,
			jti:         "",
		},
		// Null values
		{
			name:        "null_values",
			message:     []byte(`{"type":null,"jti":null}`),
			expectCache: false,
			jti:         "",
		},
		// Extra fields (should be ignored)
		{
			name:        "extra_fields",
			message:     []byte(`{"type":"add","jti":"extra-jti","expires_at":"2099-12-30T12:00:00Z","extra":"ignored"}`),
			expectCache: true,
			jti:         "extra-jti",
		},
		// Unicode JTI
		{
			name:        "unicode_jti",
			message:     []byte(`{"type":"add","jti":"유니코드-jti-테스트","expires_at":"2099-12-30T12:00:00Z"}`),
			expectCache: true,
			jti:         "유니코드-jti-테스트",
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			consumer.handleMessage(tc.message)

			if tc.jti != "" {
				inCache := blacklistCache.IsBlacklisted(tc.jti)
				if inCache != tc.expectCache {
					t.Errorf("IsBlacklisted(%s): expected %v, got %v", tc.jti, tc.expectCache, inCache)
				}
			}
		})
	}
}

func TestBlacklistConsumer_HandleMessage_Concurrent(t *testing.T) {
	blacklistCache := cache.NewBlacklistCache(1 * time.Minute)
	defer blacklistCache.Stop()

	logger := logging.NewTestLogger()
	consumer := NewBlacklistConsumer("amqp://localhost:5672", blacklistCache, logger)

	const numGoroutines = 100
	const numMessages = 100

	var wg sync.WaitGroup
	wg.Add(numGoroutines)

	for i := 0; i < numGoroutines; i++ {
		go func(id int) {
			defer wg.Done()
			for j := 0; j < numMessages; j++ {
				jti := fmt.Sprintf("concurrent-jti-%d-%d", id, j)
				msg := fmt.Sprintf(`{"type":"add","jti":"%s","expires_at":"2099-12-30T12:00:00Z"}`, jti)
				consumer.handleMessage([]byte(msg))
			}
		}(i)
	}

	wg.Wait()

	// Verify some entries are in cache
	if blacklistCache.Size() == 0 {
		t.Error("Expected cache to have entries after concurrent processing")
	}
}

func TestBlacklistEvent_Fields(t *testing.T) {
	// Test all field combinations
	tests := []struct {
		name     string
		event    BlacklistEvent
		wantType string
		wantJTI  string
	}{
		{
			name: "all fields set",
			event: BlacklistEvent{
				Type:     "add",
				JTI:      "test-jti",
				ExpireAt: time.Date(2025, 12, 30, 12, 0, 0, 0, time.UTC),
			},
			wantType: "add",
			wantJTI:  "test-jti",
		},
		{
			name: "zero time",
			event: BlacklistEvent{
				Type: "add",
				JTI:  "test-jti",
			},
			wantType: "add",
			wantJTI:  "test-jti",
		},
		{
			name:     "empty event",
			event:    BlacklistEvent{},
			wantType: "",
			wantJTI:  "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if tt.event.Type != tt.wantType {
				t.Errorf("Type: expected %s, got %s", tt.wantType, tt.event.Type)
			}
			if tt.event.JTI != tt.wantJTI {
				t.Errorf("JTI: expected %s, got %s", tt.wantJTI, tt.event.JTI)
			}
		})
	}
}

func TestBlacklistEvent_JSONRoundtrip(t *testing.T) {
	original := BlacklistEvent{
		Type:     "add",
		JTI:      "roundtrip-jti",
		ExpireAt: time.Date(2025, 12, 30, 12, 0, 0, 0, time.UTC),
	}

	// Marshal
	data, err := json.Marshal(original)
	if err != nil {
		t.Fatalf("Failed to marshal: %v", err)
	}

	// Unmarshal
	var decoded BlacklistEvent
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("Failed to unmarshal: %v", err)
	}

	// Verify
	if decoded.Type != original.Type {
		t.Errorf("Type mismatch: %s != %s", decoded.Type, original.Type)
	}
	if decoded.JTI != original.JTI {
		t.Errorf("JTI mismatch: %s != %s", decoded.JTI, original.JTI)
	}
	if !decoded.ExpireAt.Equal(original.ExpireAt) {
		t.Errorf("ExpireAt mismatch: %v != %v", decoded.ExpireAt, original.ExpireAt)
	}
}

func TestConstants(t *testing.T) {
	// Verify constants are set correctly
	if exchangeName != "blacklist.events" {
		t.Errorf("exchangeName: expected 'blacklist.events', got '%s'", exchangeName)
	}
	if exchangeType != "fanout" {
		t.Errorf("exchangeType: expected 'fanout', got '%s'", exchangeType)
	}
	if reconnectDelay != 5*time.Second {
		t.Errorf("reconnectDelay: expected 5s, got %v", reconnectDelay)
	}
}

func TestNewBlacklistConsumer_Fields(t *testing.T) {
	blacklistCache := cache.NewBlacklistCache(1 * time.Minute)
	defer blacklistCache.Stop()

	logger := logging.NewTestLogger()

	testCases := []struct {
		name    string
		amqpURL string
	}{
		{"standard url", "amqp://localhost:5672"},
		{"with credentials", "amqp://user:pass@localhost:5672"},
		{"with vhost", "amqp://localhost:5672/vhost"},
		{"empty url", ""},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			consumer := NewBlacklistConsumer(tc.amqpURL, blacklistCache, logger)

			if consumer.amqpURL != tc.amqpURL {
				t.Errorf("amqpURL: expected '%s', got '%s'", tc.amqpURL, consumer.amqpURL)
			}
			if consumer.cache != blacklistCache {
				t.Error("cache not set correctly")
			}
			if consumer.logger != logger {
				t.Error("logger not set correctly")
			}
			if consumer.done == nil {
				t.Error("done channel not initialized")
			}
		})
	}
}

func BenchmarkHandleMessage(b *testing.B) {
	blacklistCache := cache.NewBlacklistCache(1 * time.Minute)
	defer blacklistCache.Stop()

	logger := logging.NewTestLogger()
	consumer := NewBlacklistConsumer("amqp://localhost:5672", blacklistCache, logger)

	message := []byte(`{"type":"add","jti":"bench-jti","expires_at":"2099-12-30T12:00:00Z"}`)

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		consumer.handleMessage(message)
	}
}

func BenchmarkHandleMessage_Concurrent(b *testing.B) {
	blacklistCache := cache.NewBlacklistCache(1 * time.Minute)
	defer blacklistCache.Stop()

	logger := logging.NewTestLogger()
	consumer := NewBlacklistConsumer("amqp://localhost:5672", blacklistCache, logger)

	message := []byte(`{"type":"add","jti":"bench-concurrent-jti","expires_at":"2099-12-30T12:00:00Z"}`)

	b.ResetTimer()
	b.RunParallel(func(pb *testing.PB) {
		for pb.Next() {
			consumer.handleMessage(message)
		}
	})
}
