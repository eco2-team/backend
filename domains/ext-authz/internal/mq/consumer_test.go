package mq

import (
	"encoding/json"
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
		name           string
		message        []byte
		expectedInCache bool
		jti            string
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
