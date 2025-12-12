package config

import (
	"os"
	"strconv"
)

type Config struct {
	GRPCPort         int
	RedisURL         string
	JWTSecretKey     string
	JWTAlgorithm     string
	JWTIssuer        string
	JWTAudience      string
	JWTClockSkewSec  int
	JWTRequiredScope string
}

func Load() *Config {
	return &Config{
		GRPCPort:         getEnvAsInt("AUTH_GRPC_PORT", 50051), // Default to match Character gRPC port
		RedisURL:         getEnv("AUTH_REDIS_URL", "redis://localhost:6379/0"),
		JWTSecretKey:     getEnv("AUTH_SECRET_KEY", "secret"),
		JWTAlgorithm:     getEnv("AUTH_ALGORITHM", "HS256"),
		JWTIssuer:        getEnv("AUTH_ISSUER", "api.dev.growbin.app/api/v1/auth"),
		JWTAudience:      getEnv("AUTH_AUDIENCE", "api"),
		JWTClockSkewSec:  getEnvAsInt("AUTH_CLOCK_SKEW_SEC", 5),
		JWTRequiredScope: getEnv("AUTH_REQUIRED_SCOPE", ""), // optional space-delimited scope required at gateway
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
