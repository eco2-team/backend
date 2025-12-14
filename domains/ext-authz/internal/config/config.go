package config

import (
	"os"
	"strconv"
)

// Default values (tune here for system-wide changes)
const (
	// Server
	DefaultGRPCPort    = 50051
	DefaultMetricsPort = 9090

	// Redis (local dev defaults; override via env in k8s)
	DefaultRedisURL            = "redis://localhost:6379/0"
	DefaultRedisPoolSize       = 100  // go-redis default: 20 (tuned for 230 concurrent)
	DefaultRedisMinIdleConns   = 20   // warm connections to prevent cold start
	DefaultRedisPoolTimeoutMs  = 2000 // 2s - fast fail for backpressure
	DefaultRedisReadTimeoutMs  = 1000 // 1s
	DefaultRedisWriteTimeoutMs = 1000 // 1s

	// JWT (local dev defaults; override via env in k8s)
	DefaultJWTSecretKey    = "secret"
	DefaultJWTAlgorithm    = "HS256"
	DefaultJWTIssuer       = "api.dev.growbin.app/api/v1/auth"
	DefaultJWTAudience     = "api"
	DefaultJWTClockSkewSec = 5
)

type Config struct {
	GRPCPort         int
	MetricsPort      int
	RedisURL         string
	JWTSecretKey     string
	JWTAlgorithm     string
	JWTIssuer        string
	JWTAudience      string
	JWTClockSkewSec  int
	JWTRequiredScope string

	// Redis Pool Settings
	RedisPoolSize       int
	RedisMinIdleConns   int
	RedisPoolTimeoutMs  int
	RedisReadTimeoutMs  int
	RedisWriteTimeoutMs int
}

func Load() *Config {
	return &Config{
		GRPCPort:         getEnvAsInt("AUTH_GRPC_PORT", DefaultGRPCPort),
		MetricsPort:      getEnvAsInt("AUTH_METRICS_PORT", DefaultMetricsPort),
		RedisURL:         getEnv("AUTH_REDIS_URL", DefaultRedisURL),
		JWTSecretKey:     getEnv("AUTH_SECRET_KEY", DefaultJWTSecretKey),
		JWTAlgorithm:     getEnv("AUTH_ALGORITHM", DefaultJWTAlgorithm),
		JWTIssuer:        getEnv("AUTH_ISSUER", DefaultJWTIssuer),
		JWTAudience:      getEnv("AUTH_AUDIENCE", DefaultJWTAudience),
		JWTClockSkewSec:  getEnvAsInt("AUTH_CLOCK_SKEW_SEC", DefaultJWTClockSkewSec),
		JWTRequiredScope: getEnv("AUTH_REQUIRED_SCOPE", ""),

		RedisPoolSize:       getEnvAsInt("REDIS_POOL_SIZE", DefaultRedisPoolSize),
		RedisMinIdleConns:   getEnvAsInt("REDIS_MIN_IDLE_CONNS", DefaultRedisMinIdleConns),
		RedisPoolTimeoutMs:  getEnvAsInt("REDIS_POOL_TIMEOUT_MS", DefaultRedisPoolTimeoutMs),
		RedisReadTimeoutMs:  getEnvAsInt("REDIS_READ_TIMEOUT_MS", DefaultRedisReadTimeoutMs),
		RedisWriteTimeoutMs: getEnvAsInt("REDIS_WRITE_TIMEOUT_MS", DefaultRedisWriteTimeoutMs),
	}
}

func getEnv(key, fallback string) string {
	if value, exists := os.LookupEnv(key); exists {
		return value
	}
	return fallback
}

func getEnvAsInt(key string, fallback int) int {
	valueStr := getEnv(key, "")
	if value, err := strconv.Atoi(valueStr); err == nil {
		return value
	}
	return fallback
}
