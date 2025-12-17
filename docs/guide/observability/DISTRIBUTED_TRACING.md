# 분산 트레이싱 아키텍처 가이드

## 개요

ECO2 프로젝트의 분산 트레이싱 아키텍처는 **CNCF 표준**(OpenTelemetry)과 **빅테크 베스트 프랙티스**(Google, Netflix, Uber)를 참고하여 설계되었습니다.

```
┌─────────────┐     ┌─────────────────────┐     ┌─────────────┐
│   Client    │────▶│   Istio Gateway     │────▶│   Service   │
└─────────────┘     │   (trace propagate) │     │ (OTel SDK)  │
                    └─────────────────────┘     └──────┬──────┘
                                                       │ OTLP
                    ┌─────────────────────┐            ▼
                    │      Kiali          │◀───┌─────────────┐
                    │  (Service Mesh UI)  │    │   Jaeger    │
                    └─────────────────────┘    │ (istio-sys) │
                                               └──────┬──────┘
                    ┌─────────────────────┐           │
                    │      Kibana         │◀──────────┤
                    │  (Logs + Traces)    │           ▼
                    └─────────────────────┘    ┌─────────────┐
                                               │Elasticsearch│
                                               │  (Storage)  │
                                               └─────────────┘
```

---

## 빅테크 참조 아키텍처

### Google (Dapper → Cloud Trace)

| 원칙 | 설명 | ECO2 적용 |
|------|------|----------|
| **Low Overhead** | 프로덕션에서 항상 활성화 가능한 낮은 오버헤드 | 1% 샘플링 기본값 |
| **Application-level Transparency** | 개발자가 의식하지 않아도 자동 계측 | Auto-instrumentation |
| **Ubiquitous Deployment** | 모든 서비스에서 일관된 추적 | 모든 도메인 적용 |

### Netflix (Edgar)

| 원칙 | 설명 | ECO2 적용 |
|------|------|----------|
| **Request Interceptor Pattern** | HTTP/gRPC 인터셉터로 trace 전파 | FastAPI middleware |
| **Kafka-based Collection** | 비동기 수집으로 성능 영향 최소화 | OTLP async export |
| **Unified Observability** | 로그-메트릭-트레이스 통합 | ECS trace.id 연동 |

### Uber (Jaeger)

| 원칙 | 설명 | ECO2 적용 |
|------|------|----------|
| **OpenTracing → OpenTelemetry** | 표준 기반 벤더 중립적 계측 | OTel SDK 사용 |
| **Adaptive Sampling** | 트래픽에 따른 동적 샘플링 | Rate limiting sampler |
| **Context Propagation** | W3C Trace Context 전파 | Istio + OTel 연동 |

---

## CNCF 베스트 프랙티스

### 1. OpenTelemetry 통합 원칙

```yaml
# Reference: CNCF OpenTelemetry Best Practices
instrumentation:
  # 1. Auto-instrumentation 우선 사용
  auto_instrumentation: true
  
  # 2. SDK-based manual instrumentation (필요 시)
  manual_spans:
    - business_critical_operations
    - external_api_calls
  
  # 3. Context propagation
  propagators:
    - tracecontext  # W3C standard
    - baggage       # Cross-cutting concerns
```

### 2. 샘플링 전략

| 전략 | 사용 시점 | 샘플링률 |
|------|----------|---------|
| **Always On** | 개발/스테이징 | 100% |
| **Probabilistic** | 프로덕션 일반 | 1-10% |
| **Rate Limiting** | 고트래픽 서비스 | 초당 N개 |
| **Tail-based** | 에러/지연 분석 | 에러 100%, 정상 1% |

### 3. Jaeger v2 (OTel Collector 기반)

```yaml
# Jaeger v2 architecture (2024.11 GA)
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 1s
    send_batch_size: 512

exporters:
  elasticsearch:
    endpoints: ["http://elasticsearch:9200"]
    traces_index: jaeger-span

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [elasticsearch]
```

---

## ECO2 구현 아키텍처

### Python 서비스 (FastAPI)

```python
# domains/*/core/tracing.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

def configure_tracing(service_name: str, service_version: str):
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
    })
    
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint="jaeger-collector.istio-system.svc.cluster.local:4317",
        insecure=True,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

def instrument_app(app):
    FastAPIInstrumentor.instrument_app(app)
```

### Go 서비스 (ext-authz)

```go
// internal/tracing/tracing.go
import (
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
    "go.opentelemetry.io/otel/sdk/trace"
)

func InitTracer(serviceName string) (*trace.TracerProvider, error) {
    exporter, _ := otlptracegrpc.New(ctx,
        otlptracegrpc.WithEndpoint("jaeger-collector.istio-system.svc.cluster.local:4317"),
        otlptracegrpc.WithInsecure(),
    )
    
    tp := trace.NewTracerProvider(
        trace.WithBatcher(exporter),
        trace.WithResource(resource.NewWithAttributes(
            semconv.ServiceNameKey.String(serviceName),
        )),
    )
    otel.SetTracerProvider(tp)
    return tp, nil
}
```

---

## 로그-트레이스 상관관계 (Correlation)

### ECS 통합 포맷

```json
{
  "@timestamp": "2024-12-17T12:00:00.000Z",
  "message": "User login successful",
  "log.level": "info",
  "service.name": "auth-api",
  "trace.id": "abc123def456789...",
  "span.id": "0123456789abcdef",
  "user.id": "550e...0000",
  "labels": {
    "provider": "kakao"
  }
}
```

### Kibana에서 Jaeger 연동

1. **로그 → 트레이스**: `trace.id` 클릭 시 Jaeger UI로 이동
2. **트레이스 → 로그**: Jaeger span에서 관련 로그 조회

```yaml
# Kibana Discover → trace.id 필드 URL 포맷
kibana.yml:
  discover:
    customLinks:
      - label: "View in Jaeger"
        url: "https://jaeger.dev.growbin.app/trace/{{value}}"
        field: "trace.id"
```

---

## Istio + Kiali 통합

### Istio Telemetry 설정

```yaml
apiVersion: telemetry.istio.io/v1
kind: Telemetry
metadata:
  name: mesh-default
  namespace: istio-system
spec:
  tracing:
    - providers:
        - name: otel-tracing
      randomSamplingPercentage: 1.0
      customTags:
        environment:
          literal:
            value: "dev"
```

### Kiali 대시보드 기능

| 기능 | 설명 |
|------|------|
| **Service Graph** | 실시간 서비스 토폴로지 시각화 |
| **Traffic Animation** | 요청 흐름 애니메이션 |
| **Health Indicators** | 서비스별 에러율/지연 표시 |
| **Distributed Tracing** | Jaeger 연동 trace 조회 |
| **Istio Config Validation** | VirtualService/DestinationRule 검증 |

---

## OpenTelemetry Exporter 설정 전략

### 세 가지 텔레메트리 신호

OpenTelemetry는 **Traces, Metrics, Logs** 세 가지 신호를 지원합니다. ECO2에서는 각 신호별로 최적의 수집 파이프라인을 선택했습니다.

```
┌─────────────────────────────────────────────────────────────────┐
│                         ECO2 Service                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [Traces]     OTel SDK → OTLP/gRPC → Jaeger → Elasticsearch     │
│               (OTEL_TRACES_EXPORTER=otlp) ✅                    │
│                                                                 │
│  [Metrics]    prometheus-client → /metrics → Prometheus scrape  │
│               (OTEL_METRICS_EXPORTER=none) ❌ OTel 미사용       │
│                                                                 │
│  [Logs]       JSON stdout → Fluent Bit → Elasticsearch          │
│               (OTEL_LOGS_EXPORTER=none) ❌ OTel 미사용          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Kubernetes 환경변수 설정

```yaml
# workloads/domains/*/base/deployment.yaml
env:
  - name: OTEL_SERVICE_NAME
    value: "auth-api"
  - name: OTEL_TRACES_EXPORTER
    value: "otlp"                    # ✅ Jaeger로 전송
  - name: OTEL_EXPORTER_OTLP_ENDPOINT
    value: "http://jaeger-collector.istio-system.svc.cluster.local:4317"
  - name: OTEL_METRICS_EXPORTER
    value: "none"                    # ❌ Prometheus가 scrape
  - name: OTEL_LOGS_EXPORTER
    value: "none"                    # ❌ Fluent Bit가 수집
```

### 왜 Metrics/Logs는 `none`인가?

#### 1. 이미 성숙한 파이프라인 존재

| 신호 | 기존 스택 | OTel 대체 시 장점 | 전환 비용 |
|------|----------|------------------|----------|
| **Traces** | 없음 → Jaeger | ✅ 신규 도입 | 낮음 |
| **Metrics** | Prometheus (de facto 표준) | 거의 없음 | 높음 (대시보드 재작성) |
| **Logs** | Fluent Bit + EFK | Log correlation 개선 | 중간 |

#### 2. 리소스 효율성

```yaml
# OTel로 모든 신호를 보내면:
# - 네트워크 트래픽 3배 증가
# - OTel Collector 부하 증가
# - 중복 데이터 저장 (Prometheus + OTel Metrics)

# 현재 설정 (traces만):
# - 최소한의 오버헤드
# - 기존 인프라 재활용
```

#### 3. Prometheus Pull 모델의 강점

```yaml
# Prometheus Pull 모델:
# ✅ 서비스가 죽어도 "scrape 실패" 자체가 알림
# ✅ PromQL - 강력한 쿼리 언어
# ✅ Grafana 생태계 완벽 호환
# ✅ ServiceMonitor CRD로 자동 발견

# OTel Push 모델:
# ❌ 서비스가 죽으면 데이터 유실 가능
# ❌ 추가 Collector 인프라 필요
```

### 향후 전환 고려 사항

#### Logs → OTLP 전환 시점

```yaml
# 장점: 로그에 trace_id/span_id 자동 주입 (현재는 수동 구현)
# 조건: OTel Collector가 안정적으로 운영될 때
OTEL_LOGS_EXPORTER: "otlp"
```

#### Metrics → OTLP 전환 시점

```yaml
# 장점: Exemplars (메트릭 ↔ 트레이스 연결)
# 조건: Prometheus → Mimir 전환 또는 OTLP 네이티브 백엔드 사용 시
OTEL_METRICS_EXPORTER: "otlp"
```

### 설계 원칙

> **"Don't fix what isn't broken"**
>
> 기존에 잘 동작하는 Prometheus/Fluent Bit 파이프라인을 유지하면서,
> 없었던 **Traces만 OTel로 추가**하여 점진적으로 통합합니다.

---

## 프로덕션 권장 설정

### 샘플링 설정

```yaml
# 환경별 샘플링률
development:
  sampling_rate: 1.0  # 100% (디버깅용)
  
staging:
  sampling_rate: 0.1  # 10% (통합 테스트)
  
production:
  sampling_rate: 0.01  # 1% (성능 영향 최소화)
  error_sampling: 1.0  # 에러는 100% 수집
```

### 리소스 설정

```yaml
# Jaeger Collector 리소스 (프로덕션)
resources:
  requests:
    cpu: 500m
    memory: 512Mi
  limits:
    cpu: 1000m
    memory: 1Gi
```

### 데이터 보존 정책

| 데이터 유형 | 보존 기간 | 이유 |
|------------|----------|------|
| Traces (정상) | 7일 | 비용 효율 |
| Traces (에러) | 30일 | 장애 분석 |
| Service Maps | 실시간 | Kiali 용 |

---

## 트러블슈팅

### trace_id가 로그에 없는 경우

1. OpenTelemetry SDK 초기화 확인
2. Instrumentation 적용 확인
3. Context propagation 설정 확인

```python
# 디버깅: 현재 span 상태 확인
from opentelemetry import trace
span = trace.get_current_span()
print(f"Valid: {span.get_span_context().is_valid}")
```

### Jaeger에 트레이스가 안 보이는 경우

1. NetworkPolicy 확인 (4317/4318 포트)
2. Jaeger Collector 상태 확인
3. OTLP exporter 엔드포인트 확인

```bash
# NetworkPolicy 확인
kubectl get networkpolicy -n auth allow-jaeger-egress -o yaml

# Jaeger Collector 로그
kubectl logs -n istio-system -l app.kubernetes.io/name=jaeger -c jaeger
```

---

## 참고 자료

### CNCF & OpenTelemetry

- [OpenTelemetry Documentation](https://opentelemetry.io/docs/) - 공식 OTel 문서
- [Jaeger Documentation](https://www.jaegertracing.io/docs/latest/) - Jaeger v2 공식 문서

### 빅테크 아키텍처

- [Google Dapper Paper](https://research.google/pubs/dapper-a-large-scale-distributed-systems-tracing-infrastructure/) - 분산 트레이싱의 시초가 된 Google 논문
- [Uber: Evolving Distributed Tracing](https://www.uber.com/blog/distributed-tracing/) - Uber의 Jaeger 개발 배경
- [Netflix: Lessons from Building Observability Tools](https://netflixtechblog.com/lessons-from-building-observability-tools-at-netflix-7cfafed6ab17) - Netflix의 Observability 구축 경험

### Service Mesh Integration

- [Istio Distributed Tracing](https://istio.io/latest/docs/tasks/observability/distributed-tracing/) - Istio 트레이싱 설정 가이드
- [Kiali Documentation](https://kiali.io/docs/) - Service Mesh 시각화 도구
