# 이코에코(Eco²) Observability 시리즈

> **프로젝트**: Eco² Backend  
> **주제**: 마이크로서비스 환경의 Observability 구축  
> **기간**: 2025-12-17 ~

---

## 📚 시리즈 목차

| # | 제목 | 상태 | 핵심 내용 |
|---|------|------|----------|
| 0 | [로깅 파이프라인 아키텍처 설계](./00-architecture-design.md) | ✅ 완료 | 기술 스택 선정, ECK vs Helm |
| 1 | [로깅 파이프라인 구축](./01-efk-stack-setup.md) | ✅ 완료 | ECK Operator, ES, Kibana, Fluent Bit |
| 2 | [로깅 정책 수립](./02-logging-policy.md) | ✅ 완료 | 빅테크 사례, ECS 스키마 |
| 3 | [도메인별 ECS 구조화 로깅](./03-ecs-structured-logging.md) | ✅ 완료 | Python 구현, OpenTelemetry |
| 4 | [분산 트레이싱 통합](./04-distributed-tracing.md) | ✅ 완료 | Kiali, Jaeger, ServiceEntry |
| 5 | [Kibana 대시보드 구성](./05-kibana-dashboard.md) | ⚠️ 폐기 | eck-custom-resources 도입 실패 |
| 6 | [로그 기반 알림 연동](./06-alerting.md) | 📝 예정 | Watcher, Slack |
| 7 | [인덱스 전략 및 라이프사이클](./07-index-lifecycle.md) | ✅ 완료 | 앱/인프라 분리, ILM |
| 8 | [트러블슈팅](./08-troubleshooting.md) | ✅ 완료 | Fluent Bit Retry, Redis 연결 |
| 9 | [Elasticsearch 트러블슈팅](./09-elasticsearch-troubleshooting.md) | ✅ 완료 | Health Yellow, 메모리 부족, ECK 설정 |
| 10 | [eck-custom-resources 포스트모템](./10-eck-custom-resources-postmortem.md) | ✅ 완료 | 도입 실패 사례, 2시간 소요 |
| 11 | [분산 트레이싱 트러블슈팅](./11-distributed-tracing-troubleshooting.md) | ✅ 완료 | NetworkPolicy Zipkin 포트 누락 |

---

## 🎯 시리즈 목표

1. **중앙 집중화된 로깅**: 15개 노드의 로그를 한 곳에서 조회
2. **구조화된 로깅**: ECS 기반 JSON 포맷으로 쿼리 가능성 확보
3. **분산 트레이싱**: trace_id로 로그-트레이스 연결
4. **시각화 및 알림**: 실시간 모니터링 및 장애 감지

---

## 🔧 기술 스택

| 컴포넌트 | 도구 | 버전 |
|----------|------|------|
| Operator | ECK (Elastic Cloud on Kubernetes) | 2.11.0 |
| 저장소 | Elasticsearch | 8.11.0 |
| 시각화 | Kibana | 8.11.0 |
| 수집기 | Fluent Bit | 2.2.0 |
| 트레이싱 | Jaeger | All-in-One |
| 서비스 메시 | Istio + Kiali | - |
| 계측 | OpenTelemetry | 0.50b0 |

---

## 📂 관련 문서

- [ADR-001: 로깅 아키텍처 선택](../../decisions/ADR-001-logging-architecture.md)
- [로깅 정책 문서](../../guide/logging/LOGGING_POLICY.md)
- [로깅 베스트 프랙티스](../../guide/logging/LOGGING_BEST_PRACTICES.md)
- [ECK CRD 참조](../../infrastructure/ECK-CRD-REFERENCE.md)

---

## 📂 관련 코드

```
workloads/
├── logging/
│   └── base/
│       ├── elasticsearch.yaml
│       ├── kibana.yaml
│       ├── fluent-bit.yaml
│       ├── stack-config-policy.yaml  # ILM, Index Templates (GitOps)
│       └── network-policy.yaml
├── routing/
│   └── global/
│       ├── external-services.yaml
│       ├── telemetry.yaml
│       └── jaeger-destination-rule.yaml
├── network-policies/
│   └── base/
│       ├── allow-observability.yaml
│       └── allow-jaeger-egress.yaml
└── secrets/
    └── external-secrets/
        └── dev/
            └── logging-secrets.yaml

domains/
├── auth/
│   └── core/
│       ├── logging.py      # ECS JSON Formatter
│       ├── constants.py    # SERVICE_VERSION = "1.0.7"
│       └── redis.py        # health_check_interval
├── character/
│   └── core/logging.py     # ✅ 적용 완료
├── chat/
│   └── core/logging.py     # ✅ 적용 완료
├── scan/
│   └── core/logging.py     # ✅ 적용 완료
├── my/
│   └── core/logging.py     # ✅ 적용 완료
├── location/
│   └── core/logging.py     # ✅ 적용 완료
└── image/
    └── core/logging.py     # ✅ 적용 완료
```

---

## 🔗 외부 참고 자료

- [Elastic Cloud on Kubernetes (ECK)](https://www.elastic.co/guide/en/cloud-on-k8s/current/index.html)
- [Elastic Common Schema (ECS)](https://www.elastic.co/guide/en/ecs/current/index.html)
- [Fluent Bit Documentation](https://docs.fluentbit.io/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
- [Kiali Documentation](https://kiali.io/docs/)
- [Jaeger Documentation](https://www.jaegertracing.io/docs/)

---

## 📝 작성 가이드

각 글은 다음 구조를 따릅니다:

1. **개요**: 이 글에서 다루는 내용 요약
2. **목표**: 달성하려는 목표 목록
3. **단계별 구현**: 실제 코드와 설정
4. **결과 확인**: 스크린샷 또는 검증 명령어
5. **트러블슈팅**: 발생한 문제와 해결 방법
6. **다음 글 미리보기**: 시리즈 연결

---

## 📊 PR 이력

| PR | 제목 | 주요 변경 |
|----|------|----------|
| #143 | Kiali, Jaeger, OpenTelemetry 통합 | 트레이싱 인프라 |
| #145-147 | ECK 기반 EFK 로깅 스택 구축 | 로깅 인프라 |
| #149 | EFK 스택 구축 및 Observability 강화 | 통합 |
| #150 | ECS 기반 구조화된 로깅 및 정책 문서 | 로깅 구현 |
| #151 | PostSync Job 제거 + OpenTelemetry 버전 수정 | 안정화 |

