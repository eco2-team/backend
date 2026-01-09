package main

import (
	"context"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	authv3 "github.com/envoyproxy/go-control-plane/envoy/service/auth/v3"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/redis/go-redis/v9"
	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"google.golang.org/grpc"

	"github.com/eco2-team/backend/domains/ext-authz/internal/cache"
	"github.com/eco2-team/backend/domains/ext-authz/internal/config"
	"github.com/eco2-team/backend/domains/ext-authz/internal/constants"
	"github.com/eco2-team/backend/domains/ext-authz/internal/jwt"
	"github.com/eco2-team/backend/domains/ext-authz/internal/logging"
	"github.com/eco2-team/backend/domains/ext-authz/internal/mq"
	"github.com/eco2-team/backend/domains/ext-authz/internal/server"
	"github.com/eco2-team/backend/domains/ext-authz/internal/store"
	"github.com/eco2-team/backend/domains/ext-authz/internal/tracing"
)

func main() {
	cfg := config.Load()

	// Initialize structured logger
	logLevel := slog.LevelInfo
	if os.Getenv(constants.EnvLogLevel) == constants.LogLevelDebug {
		logLevel = slog.LevelDebug
	}
	logging.Init(&logging.Config{
		Level:       logLevel,
		Output:      os.Stdout,
		Environment: os.Getenv(constants.EnvEnvironment),
	})
	logger := logging.Default()

	ctx, cancel := context.WithTimeout(context.Background(), constants.InitTimeout)
	defer cancel()

	// Initialize OpenTelemetry tracing
	logger.Info("Initializing OpenTelemetry tracing",
		slog.String("otel_enabled", os.Getenv("OTEL_ENABLED")),
		slog.String("otel_endpoint", os.Getenv("OTEL_EXPORTER_OTLP_ENDPOINT")),
	)
	tp, err := tracing.Init(ctx, nil)
	if err != nil {
		logger.Error("Failed to initialize tracing", slog.String("error", err.Error()))
		// Continue without tracing - not fatal
	} else if tp != nil {
		logger.Info("OpenTelemetry tracing initialized successfully")
		defer func() {
			shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), constants.GracefulShutdownTimeout)
			defer shutdownCancel()
			if err := tp.Shutdown(shutdownCtx); err != nil {
				logger.Error("Failed to shutdown tracing", slog.String("error", err.Error()))
			}
		}()
	} else {
		logger.Warn("OpenTelemetry tracing disabled (tp is nil)")
	}

	// Initialize JWT verifier first (no external dependencies)
	verifier, err := jwt.NewVerifier(
		cfg.JWTSecretKey,
		cfg.JWTAlgorithm,
		cfg.JWTIssuer,
		cfg.JWTAudience,
		time.Duration(cfg.JWTClockSkewSec)*time.Second,
		cfg.JWTRequiredScope,
	)
	if err != nil {
		logger.Error("Failed to create JWT verifier", slog.String("error", err.Error()))
		os.Exit(1)
	}
	logger.Info("JWT verifier initialized",
		slog.String("algorithm", cfg.JWTAlgorithm),
		slog.String("issuer", cfg.JWTIssuer),
	)

	var authServer *server.AuthorizationServer
	var blacklistCache *cache.BlacklistCache
	var mqConsumer *mq.BlacklistConsumer

	if cfg.LocalCacheEnabled {
		// Local Cache Mode: Bootstrap from Redis, then use in-memory cache
		logger.Info("Local cache mode enabled",
			slog.Int("cleanup_interval_sec", cfg.LocalCacheCleanupInterval),
		)

		// Connect to Redis for bootstrap only
		redisOpts, err := redis.ParseURL(cfg.RedisURL)
		if err != nil {
			logger.Error("Failed to parse Redis URL", slog.String("error", err.Error()))
			os.Exit(1)
		}
		redisClient := redis.NewClient(redisOpts)
		defer redisClient.Close()

		// Bootstrap: Load existing blacklist from Redis
		logger.Info("Bootstrapping blacklist from Redis...")
		items, err := cache.BootstrapFromRedis(ctx, redisClient, logger)
		if err != nil {
			logger.Error("Failed to bootstrap from Redis", slog.String("error", err.Error()))
			os.Exit(1)
		}

		// Create local cache and load bootstrap data
		cleanupInterval := time.Duration(cfg.LocalCacheCleanupInterval) * time.Second
		blacklistCache = cache.NewBlacklistCache(cleanupInterval)
		loaded := blacklistCache.LoadBulk(items)
		logger.Info("Blacklist cache initialized",
			slog.Int("loaded_entries", loaded),
		)

		// Start MQ consumer for real-time updates
		if cfg.AMQPURL != "" {
			mqConsumer = mq.NewBlacklistConsumer(cfg.AMQPURL, blacklistCache, logger)
			mqConsumer.Start()
			logger.Info("MQ consumer started for blacklist sync",
				slog.String("amqp_url", maskURL(cfg.AMQPURL)),
			)
		} else {
			logger.Warn("AMQP_URL not configured, blacklist updates will not be received")
		}

		// Create server with local cache
		authServer, err = server.NewWithCache(verifier, blacklistCache, cfg.CORSAllowedOrigins)
		if err != nil {
			logger.Error("Failed to create auth server", slog.String("error", err.Error()))
			os.Exit(1)
		}
	} else {
		// Redis Mode: Every request checks Redis (legacy behavior)
		logger.Info("Redis mode (local cache disabled)")

		poolOpts := &store.PoolOptions{
			PoolSize:     cfg.RedisPoolSize,
			MinIdleConns: cfg.RedisMinIdleConns,
			PoolTimeout:  time.Duration(cfg.RedisPoolTimeoutMs) * time.Millisecond,
			ReadTimeout:  time.Duration(cfg.RedisReadTimeoutMs) * time.Millisecond,
			WriteTimeout: time.Duration(cfg.RedisWriteTimeoutMs) * time.Millisecond,
		}
		logger.Info("Redis pool configuration",
			slog.Int("pool_size", poolOpts.PoolSize),
			slog.Int("min_idle_conns", poolOpts.MinIdleConns),
			slog.Duration("pool_timeout", poolOpts.PoolTimeout),
		)

		redisStore, err := store.New(ctx, cfg.RedisURL, poolOpts)
		if err != nil {
			logger.Error("Failed to connect to Redis", slog.String("error", err.Error()))
			os.Exit(1)
		}
		defer redisStore.Close()
		logger.Info("Redis connection established")

		authServer, err = server.New(verifier, redisStore, cfg.CORSAllowedOrigins)
		if err != nil {
			logger.Error("Failed to create auth server", slog.String("error", err.Error()))
			os.Exit(1)
		}
	}

	logger.Info("CORS allowed origins configured", slog.Any("origins", cfg.CORSAllowedOrigins))

	// Start metrics server
	go func() {
		mux := http.NewServeMux()
		mux.Handle(constants.PathMetrics, promhttp.Handler())
		mux.HandleFunc(constants.PathHealth, func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte(constants.HealthOK))
		})
		mux.HandleFunc(constants.PathReady, func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte(constants.HealthOK))
		})
		metricsAddr := fmt.Sprintf(":%d", cfg.MetricsPort)
		logger.Info("Starting metrics server", slog.String("address", metricsAddr))
		if err := http.ListenAndServe(metricsAddr, mux); err != nil {
			logger.Error("Metrics server error", slog.String("error", err.Error()))
		}
	}()

	// Start gRPC server with OTEL instrumentation
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", cfg.GRPCPort))
	if err != nil {
		logger.Error("Failed to listen", slog.String("error", err.Error()))
		os.Exit(1)
	}

	// Add OTEL gRPC interceptors for distributed tracing
	grpcServer := grpc.NewServer(
		grpc.StatsHandler(otelgrpc.NewServerHandler()),
	)
	authv3.RegisterAuthorizationServer(grpcServer, authServer)

	go func() {
		logger.Info("Starting ext-authz gRPC server",
			slog.Int("port", cfg.GRPCPort),
			slog.String("service", constants.ServiceName),
			slog.String("version", constants.ServiceVersion),
		)
		if err := grpcServer.Serve(lis); err != nil {
			logger.Error("Failed to serve", slog.String("error", err.Error()))
			os.Exit(1)
		}
	}()

	// Graceful shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logger.Info("Shutting down gRPC server")
	grpcServer.GracefulStop()

	// Cleanup local cache components
	if mqConsumer != nil {
		mqConsumer.Stop()
		logger.Info("MQ consumer stopped")
	}
	if blacklistCache != nil {
		blacklistCache.Stop()
		logger.Info("Blacklist cache stopped")
	}

	logger.Info("Server stopped")
}

// maskURL masks sensitive parts of a URL for logging
func maskURL(url string) string {
	// Simple masking: show protocol and host, hide credentials
	// Example: amqp://user:pass@host:5672/ -> amqp://***@host:5672/
	if len(url) > 10 {
		return url[:10] + "***"
	}
	return "***"
}
