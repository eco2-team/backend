# Fluent Bit CRI Parser 설정 트러블슈팅

> **작업일**: 2025-12-18  
> **소요시간**: 약 30분  
> **결과**: ✅ 해결

## 📋 요약

Elasticsearch에 수집된 로그가 JSON 파싱 없이 raw 문자열로 저장되는 문제 발생. 
원인은 containerd 런타임 환경에서 Docker parser를 사용한 것이었으며, CRI parser로 변경하여 해결.

---

## 🎯 문제 상황

### 증상
Kibana에서 로그 확인 시, `log` 필드에 CRI 형식 전체가 raw 문자열로 저장됨:

```json
{
  "log": "2025-12-18T00:25:46.032696223+09:00 stdout F {\"@timestamp\": \"2025-12-17T15:25:46.032+00:00\", \"message\": \"Attempting to instrument...\", \"log.level\": \"warning\"}"
}
```

**기대했던 결과:**
```json
{
  "stream": "stdout",
  "log_processed": {
    "@timestamp": "2025-12-17T15:25:46.032+00:00",
    "message": "Attempting to instrument...",
    "log.level": "warning"
  }
}
```

---

## 🔍 원인 분석

### 1. Container Runtime 확인

```bash
kubectl get nodes -o wide
```

| 노드 | Container Runtime |
|------|-------------------|
| k8s-api-auth | **containerd://2.1.5** |
| k8s-api-character | **containerd://2.1.5** |
| ... | containerd |

**발견**: 모든 노드가 **containerd** 런타임을 사용 중.

### 2. 로그 파일 형식 비교

#### Docker 로그 형식 (JSON)
```json
{"log":"Hello World\n","stream":"stdout","time":"2025-01-01T00:00:00.000Z"}
```

#### CRI 로그 형식 (containerd)
```
2025-12-18T02:29:52.760924368+09:00 stderr F {"level":"info","msg":"..."}
│                                    │      │ └── 실제 JSON 로그
│                                    │      └── Flag (F=Full, P=Partial)
│                                    └── Stream (stdout/stderr)
└── CRI Timestamp
```

### 3. 기존 Fluent Bit 설정 문제

```yaml
# ❌ 잘못된 설정
[INPUT]
    Name              tail
    Path              /var/log/containers/*.log
    Parser            docker    # Docker 형식 파서 사용
```

**문제점**: `docker` parser는 JSON 형식만 파싱 가능. CRI 형식의 로그는 파싱 실패.

---

## 🔧 해결 방법

### 1. CRI Parser 추가

```yaml
# parsers.conf
[PARSER]
    Name        cri
    Format      regex
    Regex       ^(?<time>[^ ]+) (?<stream>stdout|stderr) (?<logtag>[^ ]*) (?<log>.*)$
    Time_Key    time
    Time_Format %Y-%m-%dT%H:%M:%S.%L%z
    Time_Keep   On
```

### 2. INPUT 설정 변경

```yaml
# fluent-bit.conf
[INPUT]
    Name              tail
    Tag               kube.*
    Path              /var/log/containers/*.log
    Parser            cri    # ✅ CRI 파서로 변경
    DB                /fluent-bit/db/flb_kube.db
    Mem_Buf_Limit     50MB
    Skip_Long_Lines   On
    Refresh_Interval  10
```

### 3. Kubernetes Filter (JSON 병합)

```yaml
[FILTER]
    Name                kubernetes
    Match               kube.*
    Kube_URL            https://kubernetes.default.svc:443
    Merge_Log           On           # JSON 로그 자동 파싱
    Merge_Log_Key       log_processed # 파싱 결과 저장 키
    K8S-Logging.Parser  On
    Labels              On
```

### 4. 전체 파이프라인 흐름

```
┌─────────────────────────────────────────────────────────────────────────┐
│  CRI 로그 파일                                                           │
│  2025-12-18T02:29:52.760Z stderr F {"level":"info","msg":"Hello"}      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  CRI Parser                                                              │
│  time: 2025-12-18T02:29:52.760Z                                         │
│  stream: stderr                                                          │
│  logtag: F                                                               │
│  log: {"level":"info","msg":"Hello"}                                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Kubernetes Filter (Merge_Log)                                           │
│  stream: stderr                                                          │
│  logtag: F                                                               │
│  log: {"level":"info","msg":"Hello"}                                    │
│  log_processed:                                                          │
│    level: info                                                           │
│    msg: Hello                                                            │
│  k8s_namespace_name: auth                                                │
│  k8s_pod_name: auth-api-xxx                                              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Elasticsearch                                                           │
│  인덱스: logs-2025.12.18                                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## ✅ 결과 확인

### 적용 후 로그 샘플

```json
{
  "timestamp": "2025-12-17T18:59:58.713Z",
  "namespace": "auth",
  "container": "ext-authz",
  "stream": "stdout",
  "log_processed": {
    "@timestamp": "2025-12-17T18:59:58.713336366Z",
    "log_level": "INFO",
    "msg": "Starting metrics server",
    "ecs": { "version": "8.11" },
    "service": {
      "name": "ext-authz",
      "version": "1.0.7",
      "environment": ""
    },
    "address": ":9090"
  }
}
```

### 검색 가능한 필드

| 필드 | 설명 | 예시 값 |
|------|------|---------|
| `stream` | stdout/stderr | `stdout` |
| `logtag` | Full/Partial | `F` |
| `log_processed.log_level` | 로그 레벨 | `INFO`, `ERROR` |
| `log_processed.msg` | 로그 메시지 | `Starting metrics server` |
| `log_processed.service.name` | 서비스명 | `ext-authz` |
| `k8s_namespace_name` | 네임스페이스 | `auth` |
| `k8s_pod_name` | Pod 이름 | `ext-authz-xxx` |

---

## 📝 교훈

### 1. Container Runtime 확인 필수
- Kubernetes 클러스터 구축 시 컨테이너 런타임 확인
- Docker → containerd 마이그레이션 트렌드로 CRI 형식이 기본

### 2. Fluent Bit Parser 선택 기준

| Container Runtime | 로그 형식 | 권장 Parser |
|-------------------|----------|-------------|
| Docker | JSON | `docker` |
| containerd | CRI | `cri` |
| CRI-O | CRI | `cri` |

### 3. Merge_Log 동작 이해
- `Merge_Log On`: `log` 필드가 JSON이면 파싱하여 병합
- `Merge_Log_Key`: 파싱 결과를 저장할 키 지정 (미지정 시 루트에 병합)

---

## 📚 참고 자료

- [Fluent Bit - CRI Parser](https://docs.fluentbit.io/manual/pipeline/parsers/configuring-parser#cri)
- [Kubernetes - Container Runtime Interface](https://kubernetes.io/docs/concepts/architecture/cri/)
- [Fluent Bit - Kubernetes Filter](https://docs.fluentbit.io/manual/pipeline/filters/kubernetes)

---

## 🗂️ 관련 파일

- `workloads/logging/base/fluent-bit.yaml` - Fluent Bit 설정
- `docs/monitoring/EFK_LOGGING_PLAN.md` - EFK 로깅 계획
