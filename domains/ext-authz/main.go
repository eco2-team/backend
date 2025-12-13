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

func main() {
	// 1. Load Config
	cfg := config.Load()

	// 2. Initialize Components
	// Use a context with timeout for initialization to avoid hanging
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	redisStore, err := store.New(ctx, cfg.RedisURL)
	if err != nil {
		log.Fatalf("Failed to connect to Redis: %v", err)
	}
	defer redisStore.Close()

	verifier := jwt.NewVerifier(
		cfg.JWTSecretKey,
		cfg.JWTAlgorithm,
		cfg.JWTIssuer,
		cfg.JWTAudience,
		time.Duration(cfg.JWTClockSkewSec)*time.Second,
		cfg.JWTRequiredScope,
	)
	authServer := server.New(verifier, redisStore)

	// 3. Start Prometheus metrics server
	go func() {
		mux := http.NewServeMux()
		mux.Handle("/metrics", promhttp.Handler())
		mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte("ok"))
		})
		mux.HandleFunc("/ready", func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte("ok"))
		})
		metricsAddr := fmt.Sprintf(":%d", cfg.MetricsPort)
		log.Printf("📊 Starting metrics server on %s", metricsAddr)
		if err := http.ListenAndServe(metricsAddr, mux); err != nil {
			log.Printf("Metrics server error: %v", err)
		}
	}()

	// 4. Start gRPC Server
	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", cfg.GRPCPort))
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	grpcServer := grpc.NewServer()
	authv3.RegisterAuthorizationServer(grpcServer, authServer)

	// Graceful Shutdown
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
