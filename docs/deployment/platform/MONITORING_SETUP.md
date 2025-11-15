# Ecoeco 13-Node Monitoring Stack

## 📊 개요

Ecoeco의 13-Node Microservices Architecture를 위한 완전한 모니터링 스택입니다.

### 아키텍처 구성

```
┌─────────────────────────────────────────────────────────────┐
│                    Grafana Dashboard                        │
│                    (Visualization)                          │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                     Prometheus                              │
│              (Metrics Collection & Storage)                 │
└───┬────────┬────────┬────────┬────────┬────────────────────┘
    │        │        │        │        │
    ▼        ▼        ▼        ▼        ▼
┌─────┐  ┌──────┐ ┌───────┐ ┌──────┐ ┌──────────┐
│ API │  │Worker│ │Infra  │ │Nodes │ │RabbitMQ  │
│ 6개 │  │ 2개  │ │(PG/R) │ │ 13개 │ │PostgreSQL│
└─────┘  └──────┘ └───────┘ └──────┘ └──────────┘
```

## 📦 구성 요소

### 1. Prometheus (메트릭 수집)
- **역할**: 모든 서비스/노드에서 메트릭 수집 및 저장
- **스토리지**: 50GB PVC (30일 보관)
- **스크랩 주기**: 30초
- **위치**: Infrastructure Node

### 2. Grafana (시각화)
- **역할**: 메트릭 시각화 및 대시보드
- **스토리지**: 10GB PVC
- **인증**: Secret 기반 (grafana-admin)
- **위치**: Infrastructure Node

### 3. Node Exporter (노드 모니터링)
- **역할**: 13개 노드의 시스템 메트릭 수집
- **배포 방식**: DaemonSet (모든 노드)
- **메트릭**: CPU, 메모리, 디스크, 네트워크

### 4. ServiceMonitor (서비스 디스커버리)
- **역할**: Kubernetes 서비스 자동 발견
- **대상**: API 6개 + Worker 2개

## 🎯 모니터링 대상

### API Services (6개)
| Service | Endpoint | Interval | Metrics |
|---------|----------|----------|---------|
| waste-api | `:8000/metrics` | 15s | 요청률, 응답시간, 에러율 |
| auth-api | `:8000/metrics` | 30s | 인증 성공/실패, 토큰 발급 |
| userinfo-api | `:8000/metrics` | 30s | 사용자 조회, DB 연결 |
| location-api | `:8000/metrics` | 30s | 위치 검색, 캐시 히트율 |
| recycle-info-api | `:8000/metrics` | 30s | 정보 조회, 캐시 사용률 |
| chat-llm-api | `:8000/metrics` | 15s | LLM 호출, 응답시간 |

### Worker Services (2개)
| Service | Endpoint | Interval | Metrics |
|---------|----------|----------|---------|
| storage-worker | `:9090/metrics` | 30s | S3 업로드, 작업 처리율 |
| ai-worker | `:9090/metrics` | 30s | AI 추론, GPU 사용률 |

### Infrastructure Services (4개)
| Service | Endpoint | Metrics |
|---------|----------|---------|
| RabbitMQ | `:15692/metrics` | Queue 크기, 메시지 처리율 |
| PostgreSQL | `:9187/metrics` | 연결 수, 쿼리 성능 |
| Redis | `:9121/metrics` | 메모리 사용, 캐시 히트율 |
| Prometheus | `:9090/metrics` | 자체 메트릭 |

### Nodes (13개)
- **Master Node (1)**: t3a.large
- **API Nodes (6)**: t3a.medium
- **Worker Nodes (2)**: t3a.large
- **Infrastructure Nodes (4)**: t3a.medium

**Node Exporter 메트릭**:
- CPU 사용률 (idle, user, system)
- 메모리 사용률 (total, available, used)
- 디스크 사용률 (filesystem)
- 네트워크 I/O

## 🚨 Alert Rules

### API 알림
| Alert | Condition | Duration | Severity |
|-------|-----------|----------|----------|
| HighAPILatency | p95 > 1s | 5분 | warning |
| HighAPIErrorRate | 에러율 > 5% | 5분 | critical |
| APIPodDown | Pod 정지 | 2분 | critical |
| HighAPICPUUsage | CPU > 80% | 10분 | warning |
| HighAPIMemoryUsage | 메모리 > 90% | 10분 | warning |

### Worker 알림
| Alert | Condition | Duration | Severity |
|-------|-----------|----------|----------|
| HighWorkerTaskFailureRate | 실패율 > 10% | 5분 | critical |
| WorkerQueueSizeHigh | Queue > 1000 | 10분 | warning |
| WorkerPodDown | Pod 정지 | 2분 | critical |
| HighWorkerTaskDuration | p95 > 60s | 10분 | warning |

### Infrastructure 알림
| Alert | Condition | Duration | Severity |
|-------|-----------|----------|----------|
| RabbitMQDown | Pod 정지 | 2분 | critical |
| PostgreSQLDown | Pod 정지 | 2분 | critical |
| RedisDown | Pod 정지 | 2분 | critical |
| HighPostgreSQLConnectionPoolUsage | 연결 > 80% | 10분 | warning |
| HighRedisMemoryUsage | 메모리 > 90% | 10분 | warning |

### Node 알림
| Alert | Condition | Duration | Severity |
|-------|-----------|----------|----------|
| HighNodeCPUUsage | CPU > 85% | 10분 | warning |
| HighNodeMemoryUsage | 메모리 > 90% | 10분 | warning |
| HighNodeDiskUsage | 디스크 > 85% | 10분 | warning |
| NodeDown | Node 정지 | 5분 | critical |

## 📈 Grafana Dashboard

### Ecoeco 13-Node Microservices Dashboard

**패널 구성**:

1. **API Services - Request Rate** (Graph)
   - 6개 API 서비스별 요청률 (req/s)

2. **API Services - Error Rate** (Graph)
   - 6개 API 서비스별 에러율 (%)

3. **API Services - Response Time (p95)** (Graph)
   - 6개 API 서비스별 95th percentile 응답시간

4. **Worker Services - Task Processing Rate** (Graph)
   - 2개 Worker 서비스별 작업 처리율 (task/s)

5. **Worker Services - Task Failure Rate** (Graph)
   - 2개 Worker 서비스별 작업 실패율 (%)

6. **RabbitMQ - Queue Size** (Graph)
   - 큐별 대기 메시지 수

7. **Node CPU Usage (13 Nodes)** (Graph)
   - 13개 노드별 CPU 사용률 (%)

8. **Node Memory Usage (13 Nodes)** (Graph)
   - 13개 노드별 메모리 사용률 (%)

9. **Pod Status by Node** (Table)
   - 노드별 Pod 배치 현황

10. **API Services - Active Pods** (Stat)
    - 활성 API Pod 수

11. **Worker Services - Active Pods** (Stat)
    - 활성 Worker Pod 수

12. **Infrastructure - Active Services** (Stat)
    - 활성 인프라 서비스 수

## 🚀 배포

### 1. 자동 배포 (권장)

```bash
# 전체 모니터링 스택 배포
./scripts/deploy-monitoring.sh
```

### 2. 수동 배포

```bash
# 1. Node Exporter 배포 (13 Nodes)
kubectl apply -f k8s/monitoring/node-exporter.yaml

# 2. Prometheus 배포
kubectl create configmap prometheus-rules \
  --from-file=k8s/monitoring/prometheus-rules.yaml \
  --namespace=default

kubectl apply -f k8s/monitoring/prometheus-deployment.yaml

# 3. Grafana 배포
kubectl create configmap grafana-dashboards \
  --from-file=k8s/monitoring/grafana-dashboard-13nodes.json \
  --namespace=default

kubectl apply -f k8s/monitoring/grafana-deployment.yaml

# 4. ServiceMonitors 배포 (Prometheus Operator 사용 시)
kubectl apply -f k8s/monitoring/servicemonitors.yaml
```

### 3. 배포 확인

```bash
# Pod 상태 확인
kubectl get pods -l component=monitoring

# Service 확인
kubectl get svc prometheus grafana

# DaemonSet 확인 (13개 노드에 모두 배포되었는지)
kubectl get daemonset node-exporter
```

## 🔍 접속

### Prometheus

```bash
# Port Forward
kubectl port-forward svc/prometheus 9090:9090

# 브라우저
http://localhost:9090
```

**주요 쿼리**:
- API 요청률: `sum(rate(http_requests_total{job=~".*-api"}[5m])) by (service)`
- Worker 작업 처리율: `sum(rate(celery_task_total[5m])) by (worker)`
- Node CPU 사용률: `(1 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m]))) * 100`

### Grafana

```bash
# Port Forward
kubectl port-forward svc/grafana 3000:3000

# 브라우저
http://localhost:3000

# 비밀번호 확인
kubectl get secret grafana-admin -o jsonpath='{.data.password}' | base64 -d
```

**기본 인증 정보**:
- Username: `admin`
- Password: `changeme123!` (변경 권장)

## 🎨 대시보드 사용

1. Grafana 로그인 후 `Ecoeco` 폴더 이동
2. `Ecoeco 13-Node Microservices` 대시보드 선택
3. 시간 범위 선택 (기본: 최근 6시간)
4. 서비스별 메트릭 확인

**필터링**:
- 특정 서비스만 보기: 레전드 클릭
- 시간 범위 변경: 우측 상단 시간 선택
- 자동 새로고침: 30초 간격

## 🔧 커스터마이징

### 새로운 메트릭 추가

1. **FastAPI 앱에 메트릭 추가**:

```python
from prometheus_client import Counter, Histogram

# 카운터 정의
request_count = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])

# 히스토그램 정의
request_duration = Histogram('http_request_duration_seconds', 'HTTP request duration', ['method', 'endpoint'])
```

2. **Prometheus Scrape 설정 업데이트**:

`prometheus-deployment.yaml`의 ConfigMap에 새 타겟 추가

3. **Grafana 대시보드 업데이트**:

`grafana-dashboard-13nodes.json`에 새 패널 추가

### Alert Rule 추가

1. `k8s/monitoring/prometheus-rules.yaml` 수정
2. ConfigMap 업데이트:

```bash
kubectl create configmap prometheus-rules \
  --from-file=k8s/monitoring/prometheus-rules.yaml \
  --namespace=default \
  --dry-run=client -o yaml | kubectl apply -f -
```

3. Prometheus Reload:

```bash
kubectl rollout restart deployment prometheus
```

## 📊 메트릭 보관

- **Prometheus**: 30일 (50GB PVC)
- **Grafana**: 무제한 (대시보드 설정)

**장기 보관이 필요한 경우**:
- Thanos / Cortex 사용 고려
- S3 백엔드 스토리지 연결

## 🐛 트러블슈팅

### Prometheus가 메트릭을 수집하지 못함

```bash
# 타겟 상태 확인
kubectl port-forward svc/prometheus 9090:9090
# http://localhost:9090/targets 확인

# Pod 로그 확인
kubectl logs -l app=prometheus --tail=100
```

### Grafana 대시보드가 비어있음

1. Datasource 확인: Configuration > Data Sources
2. Prometheus URL 확인: `http://prometheus:9090`
3. Test 클릭하여 연결 확인

### Node Exporter가 일부 노드에서 동작하지 않음

```bash
# DaemonSet 상태 확인
kubectl get daemonset node-exporter -o wide

# 특정 노드의 Pod 로그 확인
kubectl logs -l app=node-exporter -n default --all-containers=true
```

### Alert가 발생하지 않음

```bash
# Alert 규칙 확인
kubectl get configmap prometheus-rules -o yaml

# Prometheus에서 Alert 상태 확인
# http://localhost:9090/alerts
```

## 📚 참고 자료

- [Prometheus 공식 문서](https://prometheus.io/docs/)
- [Grafana 공식 문서](https://grafana.com/docs/)
- [Node Exporter](https://github.com/prometheus/node_exporter)
- [Kubernetes Monitoring Best Practices](https://kubernetes.io/docs/tasks/debug-application-cluster/resource-usage-monitoring/)

## 🎯 다음 단계

- [ ] AlertManager 연동 (Slack/Email)
- [ ] Thanos 설정 (장기 메트릭 보관)
- [ ] Custom Metrics 추가 (비즈니스 로직)
- [ ] SLO/SLI 대시보드 생성

