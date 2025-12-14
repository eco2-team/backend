package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	authv3 "github.com/envoyproxy/go-control-plane/envoy/service/auth/v3"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"google.golang.org/grpc"

	"github.com/eco2-team/backend/domains/ext-authz/internal/config"
	"github.com/eco2-team/backend/domains/ext-authz/internal/jwt"
	"github.com/eco2-team/backend/domains/ext-authz/internal/server"
	"github.com/eco2-team/backend/domains/ext-authz/internal/store"
)

const (
	PathMetrics = "/metrics"
	PathHealth  = "/health"
	PathReady   = "/ready"
	HealthOK    = "ok"
)

func main() {
	cfg := config.Load()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	poolOpts := &store.PoolOptions{
		PoolSize:     cfg.RedisPoolSize,
		MinIdleConns: cfg.RedisMinIdleConns,
		PoolTimeout:  time.Duration(cfg.RedisPoolTimeoutMs) * time.Millisecond,
		ReadTimeout:  time.Duration(cfg.RedisReadTimeoutMs) * time.Millisecond,
		WriteTimeout: time.Duration(cfg.RedisWriteTimeoutMs) * time.Millisecond,
	}
	log.Printf("🔧 Redis pool config: PoolSize=%d, MinIdleConns=%d, PoolTimeout=%v",
		poolOpts.PoolSize, poolOpts.MinIdleConns, poolOpts.PoolTimeout)

	redisStore, err := store.New(ctx, cfg.RedisURL, poolOpts)
	if err != nil {
		log.Fatalf("Failed to connect to Redis: %v", err)
	}
	defer redisStore.Close()

	verifier, err := jwt.NewVerifier(
		cfg.JWTSecretKey,
		cfg.JWTAlgorithm,
		cfg.JWTIssuer,
		cfg.JWTAudience,
		time.Duration(cfg.JWTClockSkewSec)*time.Second,
		cfg.JWTRequiredScope,
	)
	if err != nil {
		log.Fatalf("Failed to create JWT verifier: %v", err)
	}

	authServer, err := server.New(verifier, redisStore)
	if err != nil {
		log.Fatalf("Failed to create auth server: %v", err)
	}

	go func() {
		mux := http.NewServeMux()
		mux.Handle(PathMetrics, promhttp.Handler())
		mux.HandleFunc(PathHealth, func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte(HealthOK))
		})
		mux.HandleFunc(PathReady, func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte(HealthOK))
		})
		metricsAddr := fmt.Sprintf(":%d", cfg.MetricsPort)
		log.Printf("📊 Starting metrics server on %s", metricsAddr)
		if err := http.ListenAndServe(metricsAddr, mux); err != nil {
			log.Printf("Metrics server error: %v", err)
		}
	}()

	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", cfg.GRPCPort))
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	grpcServer := grpc.NewServer()
	authv3.RegisterAuthorizationServer(grpcServer, authServer)

	go func() {
		log.Printf("🚀 Starting ext-authz gRPC server on :%d", cfg.GRPCPort)
		if err := grpcServer.Serve(lis); err != nil {
			log.Fatalf("Failed to serve: %v", err)
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Println("Shutting down gRPC server...")
	grpcServer.GracefulStop()
	log.Println("Server stopped")
}
