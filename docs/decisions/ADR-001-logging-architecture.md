# ADR-001: 로깅 아키텍처 선택 (EFK → EFKL 점진적 전환)

> **Status:** Accepted  
> **Date:** 2025-12-17  
> **Updated:** 2025-12-17  
> **Deciders:** Backend Team  
> **Context:** EDA 전환을 앞둔 로깅 시스템 아키텍처 선택

---

## 📋 요약

**결정:**
1. **배포 방식:** ECK(Elastic Cloud on Kubernetes) Operator 사용
2. **아키텍처:** EFK(Elasticsearch + Fluent Bit + Kibana)로 시작하고, EDA 도입 시 Logstash CRD 추가

---

## 🔧 배포 방식 결정: ECK Operator

### 검토한 옵션

| 방식 | 장점 | 단점 |
|------|------|------|
| **StatefulSet 직접 관리** | 완전한 제어, 오버헤드 없음 | 업그레이드/TLS 수동 관리 |
| **ECK Operator** ✅ | CRD 선언적 관리, TLS 자동화, Logstash 통합 | Operator Pod ~200MB 추가 |

### ECK 선택 이유

1. **EFK → EFKL 전환 용이성**
   - Logstash CRD 추가만으로 전환 완료
   - ES ↔ Logstash 간 인증/TLS 자동 연결

2. **운영 편의성**
   - Rolling Upgrade 자동화
   - TLS 인증서 자동 생성/갱신
   - 스케일링 선언적 관리

3. **ECK 지원 컴포넌트**
   | CRD | 용도 |
   |-----|------|
   | `Elasticsearch` | 로그 저장 |
   | `Kibana` | 시각화 |
   | `Logstash` | 파이프라인 (Phase 2) |
   | `Beat` | Filebeat 대안 (옵션) |

---

## 🎯 배경

### 현재 상태
- 15개 노드 Kubernetes 클러스터
- 7개 API 서비스 (동기 방식)
- 중앙 로깅 시스템 미구축
- `k8s-logging` 노드 프로비저닝 완료 (t3.large, 8GB, 100GB)

### 고려 사항
1. 현재는 소규모 트래픽
2. 향후 EDA(Event-Driven Architecture) 도입 예정
3. EDA 도입 시 로그량 5~10배 증가 예상
4. 제한된 리소스 (8GB 단일 노드)

---

## 🔄 검토한 옵션

### 옵션 1: Fluent Bit → Elasticsearch 직접 (EFK)
```
Fluent Bit (DaemonSet) → Elasticsearch → Kibana
```

| 장점 | 단점 |
|------|------|
| 단순한 구조 | 스파이크 시 ES 부하 |
| 낮은 리소스 사용 | 복잡한 로그 변환 어려움 |
| 빠른 구축 | 버퍼 없음 |

### 옵션 2: Fluent Bit → Kafka → Logstash → Elasticsearch (EFKL)
```
Fluent Bit → Kafka → Logstash → Elasticsearch → Kibana
```

| 장점 | 단점 |
|------|------|
| 스파이크 흡수 (Kafka 버퍼) | 복잡한 구조 |
| 복잡한 로그 변환 가능 | 높은 리소스 사용 |
| 로그 재처리 가능 | 운영 복잡도 증가 |

### 옵션 3: Logstash 직접 수집 (ELK)
```
Logstash (또는 Filebeat) → Elasticsearch → Kibana
```

| 장점 | 단점 |
|------|------|
| 전통적인 방식 | Logstash 리소스 낭비 (2~4GB/노드) |
| 검증된 패턴 | Fluent Bit 대비 무거움 |

---

## 📊 로그량 분석

### 현재 (동기 방식)
```
1 API 요청 → 1~3개 로그
일일 예상: ~10,000 요청 → ~30,000 로그
```

### EDA 도입 후
```
1 API 요청 → 10~30개 로그/이벤트
- Kafka Producer/Consumer 로그
- Saga 체인 로그 (시작/완료/실패)
- CDC 이벤트 로그
- Celery 작업 로그
- 재시도/DLQ 로그

일일 예상: ~10,000 요청 → ~100,000~300,000 로그
피크 초당: ~50 msg/s
```

---

## 🔍 전환 경로 비교

### 경로 A: ELK 먼저 → Fluent Bit 추가
```
Phase 1: Filebeat/Logstash → ES → Kibana
Phase 2: Fluent Bit → Kafka → Logstash → ES → Kibana
```

**문제점:**
- Phase 1에서 Filebeat 설정 필요
- Phase 2에서 Filebeat → Fluent Bit 교체 필요
- 설정 재사용 불가, 다운타임 위험

### 경로 B: EFK 먼저 → Logstash 추가 ✅
```
Phase 1: Fluent Bit → ES → Kibana
Phase 2: Fluent Bit → Kafka → Logstash → ES → Kibana
```

**장점:**
- Fluent Bit DaemonSet 재사용 (output만 변경)
- 무중단 전환 가능
- 점진적 복잡도 증가

---

## ✅ 결정

### Phase 1 (현재): ECK 기반 EFK 구축

```
┌─────────────────────────────────────────────────────┐
│           k8s-logging (t3.large, 8GB)               │
├─────────────────────────────────────────────────────┤
│  ECK Operator (CRD 관리)                            │
│  ├─ Elasticsearch CR → 5GB heap                    │
│  └─ Kibana CR → 1GB                                │
│  Fluent Bit DaemonSet → ES 직접 전송               │
└─────────────────────────────────────────────────────┘
```

**ECK CRD 구조:**
```yaml
# Elasticsearch CR
apiVersion: elasticsearch.k8s.elastic.co/v1
kind: Elasticsearch
metadata:
  name: eco2-logs
spec:
  version: 8.11.0
  nodeSets:
  - name: default
    count: 1
    config:
      node.store.allow_mmap: false
    podTemplate:
      spec:
        nodeSelector:
          workload: logging

# Kibana CR
apiVersion: kibana.k8s.elastic.co/v1
kind: Kibana
metadata:
  name: eco2-kibana
spec:
  version: 8.11.0
  elasticsearchRef:
    name: eco2-logs  # 자동 연결
```

| 컴포넌트 | 메모리 | 역할 |
|----------|--------|------|
| ECK Operator | 200MB | CRD 컨트롤러 |
| Elasticsearch | 5GB heap | 로그 저장, 검색 |
| Kibana | 1GB | 시각화, 검색 UI |
| Fluent Bit | ~5MB/노드 | 로그 수집, 전송 |
| System | 1.8GB | OS |

### Phase 2 (EDA 도입 시): Logstash CRD 추가

```
┌─────────────────────────────────────────────────────┐
│           k8s-logging (t3.large, 8GB)               │
├─────────────────────────────────────────────────────┤
│  ECK Operator                                       │
│  ├─ Elasticsearch CR → 3GB heap                    │
│  ├─ Kibana CR → 1GB                                │
│  └─ Logstash CR → 1.5GB (NEW!)                     │
│  Fluent Bit → Kafka → Logstash CR → ES             │
└─────────────────────────────────────────────────────┘
```

**Logstash CRD 추가:**
```yaml
apiVersion: logstash.k8s.elastic.co/v1alpha1
kind: Logstash
metadata:
  name: eco2-logstash
spec:
  version: 8.11.0
  count: 1
  elasticsearchRefs:
  - name: eco2-logs
    clusterName: eco2-logs
  pipelines:
  - pipeline.id: main
    config.string: |
      input { kafka { ... } }
      filter { ... }
      output { elasticsearch { hosts => ["${ECO2_LOGS_ES_HOSTS}"] } }
```

| 컴포넌트 | 메모리 | 역할 |
|----------|--------|------|
| ECK Operator | 200MB | CRD 컨트롤러 |
| Kafka | 1GB | 로그 버퍼 (1-2시간 retention) |
| Logstash CR | 1.5GB | 파싱, trace_id 상관관계 |
| Elasticsearch CR | 3GB heap | 로그 저장 |
| Kibana CR | 1GB | 시각화 |
| System | 1.3GB | OS |

---

## 📌 전환 작업 (Phase 1 → Phase 2)

### ECK 기반 전환 장점
- Logstash CRD 추가 시 ES 연결 **자동 설정**
- TLS/인증 **자동 구성**
- 기존 Elasticsearch CR **수정만으로** 메모리 조정

| 작업 | 예상 시간 | 다운타임 |
|------|----------|----------|
| Kafka 배포 (별도) | 30분 | 없음 |
| Logstash CRD 추가 | 15분 | 없음 |
| ES CR 메모리 조정 (5GB → 3GB) | 15분 | Rolling Update |
| Fluent Bit output 변경 | 15분 | 없음 (rolling) |
| **총계** | **~1.5시간** | **~5분** |

### StatefulSet 직접 관리 대비 단축
- **30분 단축**: Logstash-ES 연결 설정 자동화
- **다운타임 감소**: ECK Rolling Update 지원

---

## 📚 참고

### Fluent Bit vs Logstash 리소스 비교
| 항목 | Fluent Bit | Logstash |
|------|------------|----------|
| 메모리 | ~5MB | ~1-4GB |
| CPU | 매우 낮음 | 중간 |
| 배포 방식 | DaemonSet | Deployment |
| 언어 | C | JRuby |

### EDA 로그 증가 예시 (스캔 → 캐릭터 획득)
```
현재: 3개 로그
EDA 후: ~16개 로그

1. scan.request (API)           → 1
2. scan.image.uploaded (Kafka)  → 2
3. scan.analysis.started        → 3
4. scan.analysis.completed      → 2
5. character.unlock.requested   → 2
6. character.unlock.completed   → 2
7. my.inventory.updated (CDC)   → 2
8. notification.sent            → 2
```

---

## 🔗 관련 문서

- [ASYNC_OBSERVABILITY_ARCHITECTURE.md](../plans/ASYNC_OBSERVABILITY_ARCHITECTURE.md)
- [eda-roadmap.md](../plans/eda-roadmap.md)

---

## 📝 이력

| 날짜 | 변경 | 작성자 |
|------|------|--------|
| 2025-12-17 | 초안 작성 | Backend Team |
| 2025-12-17 | ECK Operator 사용 결정 추가 | Backend Team |
