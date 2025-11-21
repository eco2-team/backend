# Character Service Docker Networking Guide

본 문서는 캐릭터 API를 Docker image로 빌드하여 Kubernetes에 배포할 때
PostgreSQL / Redis 같은 클러스터 내 데이터 서비스를 어떻게 참조하는지 정리한다.

## 1. Dockerfile 요약

`services/character/Dockerfile` 은 멀티 스테이지(Builder → Runtime) 구조다.

```dockerfile
FROM python:3.11-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN python -m venv /opt/venv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH"
RUN adduser --disabled-password --gecos "" appuser
COPY --from=builder /opt/venv /opt/venv
COPY ./app ./app
USER appuser
HEALTHCHECK CMD python -c "import httpx; httpx.get('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- 모든 Python 패키지는 `requirements.txt` 기반.
- 런타임 이미지는 비루트 `appuser` 로 동작.
- 컨테이너 내부에서 `/app/app/main.py` 가 FastAPI 엔트리.

## 2. 환경 변수 및 연결 정보

### 2.1 PostgreSQL

| 항목 | 값 |
|------|----|
| 환경 변수 | `CHARACTER_DATABASE_URL` |
| 기본값 (`core/config.py`) | `postgresql+asyncpg://sesacthon:sesacthon@postgres-cluster.postgres.svc.cluster.local:5432/sesacthon` |
| ConfigMap (`workloads/domains/character/base/configmap.yaml`) | 동일 값 |
| 클러스터 서비스 | `postgres-cluster.postgres.svc.cluster.local` (ClusterIP: `10.96.69.188`, Port `5432`) |

**파드 내 유효성 체크**

```bash
kubectl exec -n character deploy/character-api -- \
  env | grep CHARACTER_DATABASE_URL

kubectl exec -n character deploy/character-api -- \
  psql "postgresql://sesacthon:sesacthon@postgres-cluster.postgres.svc.cluster.local:5432/sesacthon" -c '\dt'
```

### 2.2 Redis (Sentinel 구성)

| 항목 | 값 |
|------|----|
| 네임스페이스 | `redis` |
| 서비스 | `dev-redis` (`ClusterIP: 10.102.100.72`, Ports `6379`, `26379`) |
| 엔드포인트 | `192.168.37.155`, `192.168.37.156` |
| Secret / ConfigMap | 해당 이름(`redis-config`, `redis-credentials`)은 존재하지 않음 – Helm Values 로 관리 |

서비스에서 Redis URL 을 읽는 경우 아래와 같은 패턴을 권장한다.

```bash
kubectl exec -n character deploy/character-api -- \
  env | grep REDIS
```

필요 시 ConfigMap/Secret 대신 helm values or ExternalSecret 을 통해 주입하도록 설계한다.

## 3. Docker → Kubernetes 연계 흐름

1. **Docker Build**  
   GitHub Actions (ci-services.yml)이 `services/character/Dockerfile` 로 이미지를 빌드 후 Docker Hub `docker.io/mng990/eco2` 에 푸시.

2. **ConfigMap & Secret 적용**  
   `workloads/domains/character/base/configmap.yaml` 에서 환경 변수 주입.
   Postgres URL 은 여기서 override 가능.

3. **Deployment**  
   `workloads/domains/character/base/deployment.yaml` (별도 참조) 에서 `dockerhub-secret` 으로 이미지 Pull.
   `envFrom`/`env` 섹션으로 ConfigMap 값을 컨테이너로 전달.

4. **런타임 확인**  
   파드가 정상 기동하면 `uvicorn` 이 `/health`, `/ready` 엔드포인트를 제공.

## 4. 자주 쓰는 진단 명령

```bash
# ConfigMap 값 확인
kubectl get configmap character-config -n character -o yaml

# 파드 환경 변수 확인
kubectl exec -n character deploy/character-api -- env | grep CHARACTER

# PostgreSQL 서비스 / 엔드포인트
kubectl get svc -n postgres postgres-cluster
kubectl describe svc -n postgres postgres-cluster

# Redis 서비스 / 엔드포인트
kubectl get svc -n redis
kubectl describe svc -n redis dev-redis
```

## 5. 주의사항

- 현재 Redis 접속 정보는 Helm values 로만 관리되며 ConfigMap/Secret 명칭(`redis-config`, `redis-credentials`)은 존재하지 않는다. 필요 시 ExternalSecret 추가가 필요함.
- Dockerfile 에서 설치한 `postgresql-client` 는 파드 내에서 단순 health check 용으로만 사용해야 하며, 애플리케이션 로직은 SQLAlchemy/asyncpg 를 통해 연결.
- 모든 호스트는 **클러스터 DNS 이름**을 사용해야 한다 (`*.svc.cluster.local`).

---

업데이트 시, 실제 `kubectl` 결과와 ConfigMap/Deployment 값을 함께 기록해 두면 운영팀 간 커뮤니케이션이 용이하다.


