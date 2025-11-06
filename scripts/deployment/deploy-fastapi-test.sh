#!/bin/bash
# FastAPI 테스트 서버 배포 및 통신 테스트 스크립트

set -e

MASTER_NODE=${1:-""}
MASTER_USER=${2:-"ubuntu"}

if [ -z "$MASTER_NODE" ]; then
    echo "Usage: bash $0 <MASTER_IP> [MASTER_USER]"
    echo "Example: bash $0 52.79.238.50 ubuntu"
    exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 FastAPI 테스트 서버 배포"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. FastAPI 테스트 앱 배포
echo "1️⃣ FastAPI 테스트 앱 생성"
ssh $MASTER_USER@$MASTER_NODE << 'EOF'
kubectl apply -f - <<YAML
---
# ConfigMap: FastAPI 테스트 앱 코드
apiVersion: v1
kind: ConfigMap
metadata:
  name: fastapi-test-app
  namespace: default
data:
  main.py: |
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
    import os
    import asyncpg
    import redis
    import aio_pika
    from typing import Optional
    
    app = FastAPI(title="SeSACTHON Test API")
    
    # 환경 변수
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres.default.svc.cluster.local")
    POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_DB = os.getenv("POSTGRES_DB", "sesacthon")
    POSTGRES_USER = os.getenv("POSTGRES_USER", "admin")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "changeme")
    
    REDIS_HOST = os.getenv("REDIS_HOST", "redis.default.svc.cluster.local")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    
    RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq.messaging.svc.cluster.local")
    RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
    RABBITMQ_USER = os.getenv("RABBITMQ_USER", "admin")
    RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "changeme")
    
    class HealthResponse(BaseModel):
        status: str
        postgres: str
        redis: str
        rabbitmq: str
    
    @app.get("/")
    async def root():
        return {
            "message": "SeSACTHON Test API",
            "version": "1.0.0",
            "endpoints": [
                "/health",
                "/test/postgres",
                "/test/redis",
                "/test/rabbitmq",
                "/test/all"
            ]
        }
    
    @app.get("/health", response_model=HealthResponse)
    async def health():
        """모든 서비스 상태 확인"""
        postgres_status = await test_postgres()
        redis_status = await test_redis()
        rabbitmq_status = await test_rabbitmq()
        
        all_healthy = all([
            postgres_status.get("status") == "ok",
            redis_status.get("status") == "ok",
            rabbitmq_status.get("status") == "ok"
        ])
        
        return {
            "status": "ok" if all_healthy else "degraded",
            "postgres": postgres_status.get("status", "error"),
            "redis": redis_status.get("status", "error"),
            "rabbitmq": rabbitmq_status.get("status", "error")
        }
    
    @app.get("/test/postgres")
    async def test_postgres():
        """PostgreSQL 연결 테스트"""
        try:
            conn = await asyncpg.connect(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                database=POSTGRES_DB,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                timeout=5
            )
            version = await conn.fetchval("SELECT version();")
            await conn.close()
            return {
                "status": "ok",
                "service": "PostgreSQL",
                "host": POSTGRES_HOST,
                "version": version[:50]
            }
        except Exception as e:
            return {
                "status": "error",
                "service": "PostgreSQL",
                "error": str(e)
            }
    
    @app.get("/test/redis")
    async def test_redis():
        """Redis 연결 테스트"""
        try:
            r = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                socket_connect_timeout=5
            )
            r.ping()
            r.set("test_key", "test_value", ex=10)
            value = r.get("test_key")
            r.delete("test_key")
            return {
                "status": "ok",
                "service": "Redis",
                "host": REDIS_HOST,
                "test": "write/read success"
            }
        except Exception as e:
            return {
                "status": "error",
                "service": "Redis",
                "error": str(e)
            }
    
    @app.get("/test/rabbitmq")
    async def test_rabbitmq():
        """RabbitMQ 연결 테스트"""
        try:
            connection = await aio_pika.connect_robust(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                login=RABBITMQ_USER,
                password=RABBITMQ_PASSWORD,
                timeout=5
            )
            channel = await connection.channel()
            queue = await channel.declare_queue("test_queue", auto_delete=True)
            await queue.delete()
            await connection.close()
            return {
                "status": "ok",
                "service": "RabbitMQ",
                "host": RABBITMQ_HOST,
                "test": "queue create/delete success"
            }
        except Exception as e:
            return {
                "status": "error",
                "service": "RabbitMQ",
                "error": str(e)
            }
    
    @app.get("/test/all")
    async def test_all():
        """모든 서비스 통합 테스트"""
        results = {
            "postgres": await test_postgres(),
            "redis": await test_redis(),
            "rabbitmq": await test_rabbitmq()
        }
        
        success_count = sum(1 for r in results.values() if r["status"] == "ok")
        
        return {
            "summary": {
                "total": 3,
                "success": success_count,
                "failed": 3 - success_count
            },
            "details": results
        }

  requirements.txt: |
    fastapi==0.104.1
    uvicorn[standard]==0.24.0
    asyncpg==0.29.0
    redis==5.0.1
    aio-pika==9.3.0
    pydantic==2.5.0

---
# Deployment: FastAPI 테스트 서버
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fastapi-test
  namespace: default
  labels:
    app: fastapi-test
spec:
  replicas: 2
  selector:
    matchLabels:
      app: fastapi-test
  template:
    metadata:
      labels:
        app: fastapi-test
    spec:
      nodeSelector:
        workload: application  # Worker-1 노드에 배포
      containers:
      - name: fastapi
        image: python:3.11-slim
        command:
        - /bin/bash
        - -c
        - |
          cd /app
          pip install --no-cache-dir -r requirements.txt
          uvicorn main:app --host 0.0.0.0 --port 8000
        ports:
        - containerPort: 8000
          name: http
        env:
        - name: POSTGRES_HOST
          value: "postgres.default.svc.cluster.local"
        - name: POSTGRES_PORT
          value: "5432"
        - name: POSTGRES_DB
          value: "sesacthon"
        - name: POSTGRES_USER
          value: "admin"
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: postgres-password
        - name: REDIS_HOST
          value: "redis.default.svc.cluster.local"
        - name: REDIS_PORT
          value: "6379"
        - name: RABBITMQ_HOST
          value: "rabbitmq.messaging.svc.cluster.local"
        - name: RABBITMQ_PORT
          value: "5672"
        - name: RABBITMQ_USER
          value: "admin"
        - name: RABBITMQ_PASSWORD
          valueFrom:
            secretKeyRef:
              name: rabbitmq-default-user
              key: password
        volumeMounts:
        - name: app-code
          mountPath: /app
        livenessProbe:
          httpGet:
            path: /
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 500m
            memory: 512Mi
      volumes:
      - name: app-code
        configMap:
          name: fastapi-test-app

---
# Service: ClusterIP (내부 통신 전용)
apiVersion: v1
kind: Service
metadata:
  name: fastapi-test
  namespace: default
  labels:
    app: fastapi-test
spec:
  type: ClusterIP
  selector:
    app: fastapi-test
  ports:
  - port: 8000
    targetPort: 8000
    protocol: TCP
    name: http
YAML

echo "✅ FastAPI 테스트 앱 배포 완료"
echo ""
echo "⚠️  외부 직접 접근 차단 (ALB를 통한 접근만 허용)"
EOF

# 2. Pod 상태 확인
echo ""
echo "2️⃣ Pod 상태 확인 (최대 2분 대기)"
ssh $MASTER_USER@$MASTER_NODE << 'EOF'
kubectl wait --for=condition=ready pod -l app=fastapi-test -n default --timeout=120s
kubectl get pods -l app=fastapi-test -n default -o wide
EOF

# 3. Service 정보 확인
echo ""
echo "3️⃣ Service 정보 확인"
ssh $MASTER_USER@$MASTER_NODE << 'EOF'
echo "ClusterIP Service (내부 전용):"
kubectl get svc fastapi-test -n default
EOF

# 4. 내부 통신 테스트
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🧪 내부 통신 테스트 (Pod → Services)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh $MASTER_USER@$MASTER_NODE << 'EOF'
POD_NAME=$(kubectl get pods -l app=fastapi-test -n default -o jsonpath='{.items[0].metadata.name}')

echo "테스트 Pod: $POD_NAME"
echo ""

echo "1️⃣ Root endpoint (/):"
kubectl exec -n default $POD_NAME -- curl -s http://localhost:8000/ | head -10

echo ""
echo "2️⃣ Health Check (/health):"
kubectl exec -n default $POD_NAME -- curl -s http://localhost:8000/health

echo ""
echo "3️⃣ PostgreSQL 테스트 (/test/postgres):"
kubectl exec -n default $POD_NAME -- curl -s http://localhost:8000/test/postgres

echo ""
echo "4️⃣ Redis 테스트 (/test/redis):"
kubectl exec -n default $POD_NAME -- curl -s http://localhost:8000/test/redis

echo ""
echo "5️⃣ RabbitMQ 테스트 (/test/rabbitmq):"
kubectl exec -n default $POD_NAME -- curl -s http://localhost:8000/test/rabbitmq

echo ""
echo "6️⃣ 전체 통합 테스트 (/test/all):"
kubectl exec -n default $POD_NAME -- curl -s http://localhost:8000/test/all
EOF

# 5. Ingress 리소스 생성 (ALB 통한 접근)
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📡 Ingress 리소스 생성 (ALB)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh $MASTER_USER@$MASTER_NODE << 'EOF'
kubectl apply -f - <<YAML
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: fastapi-test-ingress
  namespace: default
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: instance
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}, {"HTTPS": 443}]'
    alb.ingress.kubernetes.io/ssl-redirect: '443'
    alb.ingress.kubernetes.io/group.name: growbin-alb
    alb.ingress.kubernetes.io/group.order: '40'
    alb.ingress.kubernetes.io/backend-protocol: HTTP
    alb.ingress.kubernetes.io/healthcheck-path: /health
spec:
  ingressClassName: alb
  rules:
  - http:
      paths:
      - path: /api/v1
        pathType: Prefix
        backend:
          service:
            name: fastapi-test
            port:
              number: 8000
YAML

echo "✅ Ingress 생성 완료"
echo ""
echo "⏳ ALB 생성 대기 (약 3분)..."
sleep 10

kubectl get ingress fastapi-test-ingress -n default
EOF

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 테스트 서버 배포 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "【접근 방법】"
echo ""
echo "1️⃣ 클러스터 내부 (다른 Pod에서):"
echo "   curl http://fastapi-test.default.svc.cluster.local:8000/health"
echo ""
echo "2️⃣ ALB/Ingress (외부, 약 3분 후):"
echo "   curl https://growbin.app/api/v1/health"
echo ""
echo "⚠️  보안: 외부 직접 접근 차단됨 (ALB를 통한 접근만 허용)"
echo ""
echo "【테스트 엔드포인트】"
echo "   GET /              # API 정보"
echo "   GET /health        # 전체 상태 확인"
echo "   GET /test/postgres # PostgreSQL 연결 테스트"
echo "   GET /test/redis    # Redis 연결 테스트"
echo "   GET /test/rabbitmq # RabbitMQ 연결 테스트"
echo "   GET /test/all      # 통합 테스트"
echo ""

