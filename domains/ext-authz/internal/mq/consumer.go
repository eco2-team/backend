// Package mq provides RabbitMQ consumer for blacklist cache synchronization.
// When a user logs out, auth-api publishes an event to the blacklist.events exchange.
// This consumer receives the event and updates the local cache.
package mq

import (
	"encoding/json"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	amqp "github.com/rabbitmq/amqp091-go"

	"github.com/eco2-team/backend/domains/ext-authz/internal/cache"
	"github.com/eco2-team/backend/domains/ext-authz/internal/logging"
)

const (
	// exchangeName is the fanout exchange for blacklist events.
	exchangeName = "blacklist.events"
	// exchangeType is fanout to broadcast to all consumers.
	exchangeType = "fanout"
	// reconnectDelay is the delay before attempting to reconnect.
	reconnectDelay = 5 * time.Second
)

// Metrics for MQ consumer
var (
	mqEventsReceived = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "ext_authz",
		Subsystem: "mq",
		Name:      "events_received_total",
		Help:      "Total number of events received from RabbitMQ",
	}, []string{"type"})

	mqEventsProcessed = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "ext_authz",
		Subsystem: "mq",
		Name:      "events_processed_total",
		Help:      "Total number of events successfully processed",
	}, []string{"type"})

	mqEventsFailed = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "ext_authz",
		Subsystem: "mq",
		Name:      "events_failed_total",
		Help:      "Total number of events that failed to process",
	})

	mqConnectionStatus = promauto.NewGauge(prometheus.GaugeOpts{
		Namespace: "ext_authz",
		Subsystem: "mq",
		Name:      "connection_status",
		Help:      "Current connection status (1=connected, 0=disconnected)",
	})

	mqReconnects = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "ext_authz",
		Subsystem: "mq",
		Name:      "reconnects_total",
		Help:      "Total number of reconnection attempts",
	})
)

// BlacklistEvent represents an event from auth-api when a token is blacklisted.
type BlacklistEvent struct {
	Type     string    `json:"type"`      // "add" or "remove"
	JTI      string    `json:"jti"`       // Token identifier
	ExpireAt time.Time `json:"expires_at"` // When the token expires
}

// BlacklistConsumer consumes blacklist events from RabbitMQ.
type BlacklistConsumer struct {
	amqpURL string
	cache   *cache.BlacklistCache
	logger  *logging.Logger
	done    chan struct{}
}

// NewBlacklistConsumer creates a new BlacklistConsumer.
func NewBlacklistConsumer(amqpURL string, cache *cache.BlacklistCache, logger *logging.Logger) *BlacklistConsumer {
	return &BlacklistConsumer{
		amqpURL: amqpURL,
		cache:   cache,
		logger:  logger,
		done:    make(chan struct{}),
	}
}

// Start begins consuming events from RabbitMQ.
// It will automatically reconnect on connection failure.
func (c *BlacklistConsumer) Start() {
	go c.consumeLoop()
}

// Stop stops the consumer.
func (c *BlacklistConsumer) Stop() {
	close(c.done)
}

// consumeLoop handles connection and reconnection to RabbitMQ.
func (c *BlacklistConsumer) consumeLoop() {
	for {
		select {
		case <-c.done:
			c.logger.Info("MQ consumer stopped")
			return
		default:
			if err := c.connect(); err != nil {
				c.logger.Error("MQ connection failed",
					"error", err,
					"retry_in", reconnectDelay,
				)
				mqConnectionStatus.Set(0)
				mqReconnects.Inc()
				time.Sleep(reconnectDelay)
				continue
			}
		}
	}
}

// connect establishes a connection to RabbitMQ and starts consuming.
func (c *BlacklistConsumer) connect() error {
	conn, err := amqp.Dial(c.amqpURL)
	if err != nil {
		return err
	}
	defer conn.Close()

	ch, err := conn.Channel()
	if err != nil {
		return err
	}
	defer ch.Close()

	// Declare fanout exchange
	err = ch.ExchangeDeclare(
		exchangeName, // name
		exchangeType, // type
		true,         // durable
		false,        // auto-deleted
		false,        // internal
		false,        // no-wait
		nil,          // arguments
	)
	if err != nil {
		return err
	}

	// Declare anonymous exclusive queue
	q, err := ch.QueueDeclare(
		"",    // name (auto-generated)
		false, // durable
		true,  // delete when unused
		true,  // exclusive
		false, // no-wait
		nil,   // arguments
	)
	if err != nil {
		return err
	}

	// Bind queue to exchange
	err = ch.QueueBind(
		q.Name,       // queue name
		"",           // routing key (ignored for fanout)
		exchangeName, // exchange
		false,        // no-wait
		nil,          // arguments
	)
	if err != nil {
		return err
	}

	// Start consuming
	msgs, err := ch.Consume(
		q.Name, // queue
		"",     // consumer tag
		true,   // auto-ack
		true,   // exclusive
		false,  // no-local
		false,  // no-wait
		nil,    // arguments
	)
	if err != nil {
		return err
	}

	mqConnectionStatus.Set(1)
	c.logger.Info("MQ consumer connected",
		"exchange", exchangeName,
		"queue", q.Name,
	)

	// Process messages until connection closes or shutdown
	connClose := conn.NotifyClose(make(chan *amqp.Error))

	for {
		select {
		case <-c.done:
			return nil
		case err := <-connClose:
			c.logger.Warn("MQ connection closed", "error", err)
			mqConnectionStatus.Set(0)
			return err
		case msg := <-msgs:
			c.handleMessage(msg.Body)
		}
	}
}

// handleMessage processes a single blacklist event.
func (c *BlacklistConsumer) handleMessage(body []byte) {
	var event BlacklistEvent
	if err := json.Unmarshal(body, &event); err != nil {
		c.logger.Warn("Failed to unmarshal event",
			"error", err,
			"body", string(body),
		)
		mqEventsFailed.Inc()
		return
	}

	mqEventsReceived.WithLabelValues(event.Type).Inc()

	switch event.Type {
	case "add":
		if event.JTI == "" {
			c.logger.Warn("Received add event with empty JTI")
			mqEventsFailed.Inc()
			return
		}
		c.cache.Add(event.JTI, event.ExpireAt)
		c.logger.Debug("Added JTI to cache",
			"jti", event.JTI,
			"expire_at", event.ExpireAt,
		)
		mqEventsProcessed.WithLabelValues("add").Inc()

	case "remove":
		// Currently not used - TTL handles expiration
		c.logger.Debug("Received remove event (ignored)",
			"jti", event.JTI,
		)
		mqEventsProcessed.WithLabelValues("remove").Inc()

	default:
		c.logger.Warn("Unknown event type",
			"type", event.Type,
		)
		mqEventsFailed.Inc()
	}
}
