# Observability 강화 작업 로그 (v1.0.6)

## 1. 개요 및 목표
*   **목표:** 마이크로서비스 간의 복잡한 호출 관계를 시각화하고, E2E(End-to-End) 트랜잭션을 추적하여 시스템 투명성을 확보한다.
*   **핵심 요구사항:**
    *   OAuth 2.0 로그인부터 DB/Redis 호출까지 끊김 없는 트레이싱
    *   외부 서비스(Google, Kakao, OpenAI, S3) 의존성 시각화
    *   개발 환경(`dev`)에서의 100% 트레이스 샘플링

## 2. 아키텍처 및 도구 선정
| 컴포넌트 | 도구 | 역할 | 비고 |
|---|---|---|---|
| **Service Mesh** | Istio | 트래픽 제어 및 Telemetry 데이터 생성 | Sidecar Pattern |
| **Visualization** | Kiali | 서비스 토폴로지 시각화, 트래픽 애니메이션 | `istio-system` |
| **Tracing** | Jaeger | 분산 트레이싱 저장 및 조회 | All-in-One (Memory) |
| **Instrumentation** | OpenTelemetry | 애플리케이션 자동 계측 (Auto-Instrumentation) | Python FastAPI |
| **Metrics** | Prometheus | 메트릭 수집 및 저장 | `kube-prometheus-stack` |

## 3. 구축 과정 (Step-by-Step)

### 3.1 Observability 도구 배포 (`clusters/dev/apps/`)
*   **Kiali (`60-kiali.yaml`)**:
    *   Prometheus, Jaeger, Grafana 연동 설정
    *   익명 접속 허용 (`strategy: anonymous`)
*   **Jaeger (`61-jaeger.yaml`)**:
    *   `jaegertracing/jaeger` 차트 사용 (All-in-One)
    *   Storage: Memory (개발용)

### 3.2 네트워크 및 DNS 설정
*   **도메인 연결**:
    *   `kiali.dev.growbin.app`, `jaeger.dev.growbin.app`
    *   **ExternalDNS**: Ingress Annotation에 호스트 추가 -> Route53 자동 등록
*   **Network Policy (`allow-observability.yaml`)**:
    *   Ingress 허용: Gateway -> Kiali/Jaeger UI
    *   Collection 허용: Observability 도구 -> 워크로드 (Metrics/Trace 수집 포트)

### 3.3 OpenTelemetry Auto-Instrumentation (Backend)
*   **전략**: 코드 수정 최소화 (Zero-code change)
*   **적용 방법**:
    1.  `requirements.txt`: `opentelemetry-distro`, `opentelemetry-exporter-otlp`, `opentelemetry-instrumentation-fastapi` 등 추가
    2.  `Dockerfile`: `CMD ["opentelemetry-instrument", "uvicorn", ...]` 으로 실행 명령어 래핑
    3.  `Deployment`: 환경변수 주입
        *   `OTEL_SERVICE_NAME`: `auth-api` 등 서비스명
        *   `OTEL_EXPORTER_OTLP_ENDPOINT`: `http://jaeger-collector.istio-system.svc.cluster.local:4317`
*   **효과**: HTTP 요청뿐만 아니라 **SQL(SQLAlchemy), Redis, 외부 API(httpx)** 호출까지 자동 추적됨.

### 3.4 Service Mesh 시각화 품질 향상
*   **Trace Sampling 100%**:
    *   `workloads/routing/global/telemetry.yaml` 생성
    *   개발 환경 특성상 모든 요청을 분석하기 위해 `randomSamplingPercentage: 100.00` 설정
*   **External Services 시각화 (ServiceEntry)**:
    *   `workloads/routing/global/external-services.yaml`
    *   Google/Kakao/Naver (OAuth), OpenAI, AWS S3/CloudFront 등을 `MESH_EXTERNAL`로 정의
    *   **결과**: Kiali 그래프에서 `PassthroughCluster` 대신 **"google-oauth", "openai-external"** 등의 명확한 노드로 표시됨.
*   **Version Labeling**:
    *   모든 Deployment에 `version: v1` 라벨 일괄 적용 -> Kiali 그래프에서 워크로드 노드가 명확하게 표현됨.

## 4. 트러블슈팅 로그

### Issue 1: Kiali에서 Prometheus/Jaeger 연결 실패
*   **증상**: Kiali 대시보드에서 "Could not fetch health", "Tracing client is not initialized" 에러 발생.
*   **원인**:
    *   Prometheus URL 오설정 (`monitoring` vs `prometheus` 네임스페이스)
    *   Jaeger Service 이름 불일치 및 Grafana URL 누락
*   **해결**:
    *   `clusters/dev/apps/60-kiali.yaml` 내 `external_services` URL 수정
    *   Prometheus: `http://prometheus-operated.prometheus.svc.cluster.local:9090`
    *   Jaeger: `http://jaeger-query.istio-system.svc.cluster.local:16686`

### Issue 2: 외부 접속 불가 (NXDOMAIN)
*   **증상**: `jaeger.dev.growbin.app` 접속 시 DNS 에러.
*   **원인**: Ingress에는 호스트가 추가되었으나 `external-dns` 어노테이션에 누락되어 Route53에 등록되지 않음.
*   **해결**: `workloads/routing/gateway/dev/patch-ingress.yaml`에 호스트 목록 추가 -> ExternalDNS가 감지 후 등록.

## 5. 결과 확인 가이드 (블로그 포스팅용)

### 5.1 Kiali Graph 캡처 포인트
1.  **Display 설정**: Traffic Animation, Security, Request Distribution 활성화.
2.  **OAuth 흐름**: `Gateway` -> `Auth` -> `google-oauth` -> `Auth` -> `DB` 흐름 확인.
3.  **AI 파이프라인**: `Chat` -> `openai-external` & `aws-cloudfront` 흐름 확인.

### 5.2 Jaeger Trace 캡처 포인트
1.  **Full Transaction**: `POST /api/v1/chat/messages` 요청 검색.
2.  **Span Detail**:
    *   FastAPI Controller 진입
    *   Redis Cache 조회 (Cache Miss)
    *   OpenAI API 호출 (`httpx` span)
    *   PostgreSQL 저장 (`sqlalchemy` span)
    *   Redis Cache 갱신
3.  **Error Case**: 고의로 500 에러 유발 후 빨간색 Error Span 및 Log 확인.
