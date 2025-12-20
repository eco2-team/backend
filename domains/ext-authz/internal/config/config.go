package config

import (
	"os"
	"strconv"
	"strings"
)

// Default values (tune here for system-wide changes)
const (
	// Server
	DefaultGRPCPort    = 50051
	DefaultMetricsPort = 9090

	// Redis (local dev defaults; override via env in k8s)
	DefaultRedisURL            = "redis://localhost:6379/0"
	DefaultRedisPoolSize       = 500  // max connections per pod (tuned for high concurrency)
	DefaultRedisMinIdleConns   = 200  // warm connections to prevent cold start
	DefaultRedisPoolTimeoutMs  = 2000 // 2s - fast fail for backpressure
	DefaultRedisReadTimeoutMs  = 1000 // 1s
	DefaultRedisWriteTimeoutMs = 1000 // 1s

	// JWT (local dev defaults; override via env in k8s)
	DefaultJWTSecretKey    = "secret"
	DefaultJWTAlgorithm    = "HS256"
	DefaultJWTIssuer       = "api.dev.growbin.app/api/v1/auth"
	DefaultJWTAudience     = "api"
	DefaultJWTClockSkewSec = 5

	// CORS (comma-separated origins)
	DefaultCORSAllowedOrigins = "https://frontend.dev.growbin.app,https://frontend1.dev.growbin.app,https://frontend2.dev.growbin.app,http://localhost:5173"
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

	// CORS Settings
	CORSAllowedOrigins []string
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

		CORSAllowedOrigins: parseOrigins(getEnv("CORS_ALLOWED_ORIGINS", DefaultCORSAllowedOrigins)),
	}
}

// parseOrigins parses comma-separated origins into a slice
func parseOrigins(origins string) []string {
	if origins == "" {
		return nil
	}
	parts := strings.Split(origins, ",")
	result := make([]string, 0, len(parts))
	for _, p := range parts {
		if trimmed := strings.TrimSpace(p); trimmed != "" {
			result = append(result, trimmed)
		}
	}
	return result
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
