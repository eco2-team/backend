# Build Stage
FROM golang:1.24-alpine AS builder

WORKDIR /app

# Download dependencies
COPY apps/ext_authz/go.mod apps/ext_authz/go.sum ./
RUN go mod download

# Copy source
COPY apps/ext_authz/ .

# Run tests
RUN go test ./...

# Build
# CGO_ENABLED=0 for static binary
RUN CGO_ENABLED=0 GOOS=linux go build -o ext-authz main.go

# Run Stage
# Use distroless for security and minimal size
FROM gcr.io/distroless/static-debian12

WORKDIR /app

COPY --from=builder /app/ext-authz /app/ext-authz

# Expose gRPC port
EXPOSE 50051

CMD ["/app/ext-authz"]
