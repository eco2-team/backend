# ECK (Elastic Cloud on Kubernetes) CRD 참조

> **버전:** 2.11.0  
> **생성일:** 2025-12-17  
> **소스:** https://download.elastic.co/downloads/eck/2.11.0/crds.yaml

---

## 📋 개요

ECK Operator는 Elastic Stack 컴포넌트를 Kubernetes에서 관리하기 위한 CRD(Custom Resource Definition)를 제공합니다.

### CRD 목록

| CRD | Kind | Short Name | 용도 |
|-----|------|------------|------|
| `elasticsearches.elasticsearch.k8s.elastic.co` | Elasticsearch | `es` | 검색/로그 저장소 |
| `kibanas.kibana.k8s.elastic.co` | Kibana | `kb` | 시각화 대시보드 |
| `logstashes.logstash.k8s.elastic.co` | Logstash | `ls` | 로그 파이프라인 |
| `beats.beat.k8s.elastic.co` | Beat | - | 경량 데이터 수집기 |
| `agents.agent.k8s.elastic.co` | Agent | - | 통합 데이터 수집기 |
| `apmservers.apm.k8s.elastic.co` | ApmServer | `apm` | APM 서버 |
| `enterprisesearches.enterprisesearch.k8s.elastic.co` | EnterpriseSearch | `ent` | 엔터프라이즈 검색 |
| `elasticmapsservers.maps.k8s.elastic.co` | ElasticMapsServer | `ems` | 지도 서비스 |
| `elasticsearchautoscalers.autoscaling.k8s.elastic.co` | ElasticsearchAutoscaler | - | ES 오토스케일링 |
| `stackconfigpolicies.stackconfigpolicy.k8s.elastic.co` | StackConfigPolicy | `scp` | 스택 설정 정책 |

---

## 🔧 현재 사용 중인 CRD

### 1. Elasticsearch

```yaml
apiVersion: elasticsearch.k8s.elastic.co/v1
kind: Elasticsearch
metadata:
  name: eco2-logs
  namespace: logging
spec:
  version: 8.11.0
  nodeSets:
  - name: default
    count: 1
    config:
      node.store.allow_mmap: false
    volumeClaimTemplates:
    - metadata:
        name: elasticsearch-data
      spec:
        accessModes: [ReadWriteOnce]
        resources:
          requests:
            storage: 50Gi
```

**주요 필드:**
| 필드 | 설명 |
|------|------|
| `spec.version` | Elasticsearch 버전 |
| `spec.nodeSets` | 노드셋 구성 (count, config, podTemplate) |
| `spec.http` | HTTP 설정 (TLS 등) |
| `spec.transport` | Transport 설정 |

**생성되는 리소스:**
- StatefulSet: `<name>-es-<nodeset>`
- Service: `<name>-es-http`, `<name>-es-transport`
- Secret: `<name>-es-elastic-user` (비밀번호)
- ConfigMap: `<name>-es-config`

---

### 2. Kibana

```yaml
apiVersion: kibana.k8s.elastic.co/v1
kind: Kibana
metadata:
  name: eco2-kibana
  namespace: logging
spec:
  version: 8.11.0
  count: 1
  elasticsearchRef:
    name: eco2-logs  # ES CR 참조 → 자동 연결
```

**주요 필드:**
| 필드 | 설명 |
|------|------|
| `spec.version` | Kibana 버전 |
| `spec.count` | 레플리카 수 |
| `spec.elasticsearchRef` | 연결할 Elasticsearch CR |
| `spec.http` | HTTP 설정 (TLS 등) |
| `spec.config` | kibana.yml 설정 |

**생성되는 리소스:**
- Deployment: `<name>-kb`
- Service: `<name>-kb-http`
- Secret: ES 연결 정보 자동 주입

---

### 3. Logstash (Phase 2 예정)

```yaml
apiVersion: logstash.k8s.elastic.co/v1alpha1
kind: Logstash
metadata:
  name: eco2-logstash
  namespace: logging
spec:
  version: 8.11.0
  count: 1
  elasticsearchRefs:
  - name: eco2-logs
    clusterName: eco2-logs
  pipelines:
  - pipeline.id: main
    config.string: |
      input { ... }
      filter { ... }
      output { elasticsearch { hosts => ["${ECO2_LOGS_ES_HOSTS}"] } }
```

**주요 필드:**
| 필드 | 설명 |
|------|------|
| `spec.version` | Logstash 버전 |
| `spec.count` | 레플리카 수 |
| `spec.elasticsearchRefs` | 연결할 ES 목록 |
| `spec.pipelines` | Logstash 파이프라인 설정 |

---

## 🔒 Webhook 구성

### External Secrets vs ECK 비교

| 항목 | External Secrets | ECK |
|------|-----------------|-----|
| **Webhook 위치** | CRD 내 `conversion` 블록 | Operator가 별도 생성 |
| **서비스 이름** | `dev-external-secrets-webhook` | `elastic-webhook-server` |
| **네임스페이스** | `platform-system` | `elastic-system` |
| **패칭 필요** | ✅ 환경별 서비스명 | ❌ 불필요 |

### ECK Webhook 동작 방식

```
ECK Operator (elastic-system)
    │
    ├── ValidatingWebhookConfiguration 생성
    │   └── Service: elastic-webhook-server
    │
    └── TLS 인증서 자동 관리
        └── Secret: elastic-webhook-server-cert
```

**결론:** ECK CRD는 환경별 패칭 없이 base 스펙 그대로 사용 가능

---

## 📁 파일 구조

```
workloads/crds/
├── base/
│   └── kustomization.yaml
│       └── # ECK CRD (패칭 없이 직접 참조)
│           - https://download.elastic.co/downloads/eck/2.11.0/crds.yaml
└── dev/
    └── kustomization.yaml
        └── # External Secrets만 패칭
```

---

## 🔗 참고 링크

- [ECK 공식 문서](https://www.elastic.co/guide/en/cloud-on-k8s/current/index.html)
- [ECK CRD 다운로드](https://download.elastic.co/downloads/eck/2.11.0/crds.yaml)
- [ECK Webhook 설정](https://www.elastic.co/guide/en/cloud-on-k8s/current/k8s-webhook.html)
- [Elasticsearch CR 레퍼런스](https://www.elastic.co/guide/en/cloud-on-k8s/current/k8s-elasticsearch-specification.html)
- [Kibana CR 레퍼런스](https://www.elastic.co/guide/en/cloud-on-k8s/current/k8s-kibana.html)
- [Logstash CR 레퍼런스](https://www.elastic.co/guide/en/cloud-on-k8s/current/k8s-logstash.html)

---

## 📝 이력

| 날짜 | 변경 | 작성자 |
|------|------|--------|
| 2025-12-17 | 초안 작성 | Backend Team |
