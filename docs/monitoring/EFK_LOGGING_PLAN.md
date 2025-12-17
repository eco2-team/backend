# EFK 로깅 시스템 구축 계획 (v1.1.0)

## 1. 개요 및 목표
*   **목표:** 마이크로서비스 환경에서 분산된 로그를 중앙 집중화하고, 데이터 파이프라인(ETL) 수준의 로그 가공 및 분석 환경을 구축한다.
*   **선정 스택: EFK (Elasticsearch + Fluent Bit + Kibana)**
    *   **선정 사유:** Python/FastAPI 환경과의 호환성, Kubernetes 네이티브(DaemonSet) 구조, 리소스 효율성(Fluent Bit), 강력한 검색/분석 기능(Elasticsearch).

## 2. 아키텍처 설계

### 2.1 데이터 파이프라인 흐름
```mermaid
graph LR
    subgraph Worker Nodes
        App[FastAPI Pods] -->|stdout/stderr| ContainerLogs[/var/log/containers/]
        ContainerLogs -->|Tail| FB[Fluent Bit (DaemonSet)]
        FB -->|Filter/Parse| FB
    end
    
    subgraph Logging Node (New)
        FB -->|Forward (Chunked)| ES[Elasticsearch]
        ES -->|Query| Kibana[Kibana UI]
    end
```

### 2.2 노드 구성 및 격리 전략
*   **Logging Node (`k8s-logging`)**:
    *   **Spec:** `t3.large` (2 vCPU, 8GB RAM) - ES Heap 메모리 확보(4GB)를 위해 필수.
    *   **Taint:** `infra-type=logging:NoSchedule`
    *   **Role:** Elasticsearch 및 Kibana 전용 실행. Fluent Bit는 모든 노드에서 실행.

## 3. 구축 단계 (Implementation Phases)

### Phase 1: 인프라 프로비저닝 (Terraform)
*   **목표:** 로깅 전용 노드 추가
*   **작업 내용:**
    *   `terraform/instances.tf`: `logging` 인스턴스 정의 추가 (count = 1)
    *   `terraform/variables.tf`: `logging_instance_type` 변수 추가 (`t3.large`)
    *   `terraform/security-group.tf`: 로깅 노드 관련 SG 규칙 점검 (ES 포트 9200 내부 통신 허용)

### Phase 2: 노드 설정 (Ansible)
*   **목표:** 새 노드를 클러스터에 조인시키고 Taint 적용
*   **작업 내용:**
    *   `ansible/inventory/hosts.ini`: `[logging]` 그룹 추가
    *   `ansible/playbooks/03-worker-join.yml`: 로깅 노드 조인 및 라벨링(`infra-type=logging`), Taint 설정 자동화

### Phase 3: 애플리케이션 배포 (ArgoCD & Helm)
*   **목표:** EFK 스택 설치
*   **구성 요소:**
    1.  **Elasticsearch (StatefulSet)**
        *   Chart: `elastic/elasticsearch`
        *   설정: Single Node (개발용), Heap Size 4GB, PV 50GB, `nodeSelector: infra-type=logging`
    2.  **Kibana (Deployment)**
        *   Chart: `elastic/kibana`
        *   설정: Ingress (`kibana.dev.growbin.app`), ES 연동
    3.  **Fluent Bit (DaemonSet)**
        *   Chart: `fluent/fluent-bit`
        *   설정: Kubernetes Filter 활성화, JSON Parser 설정, Output -> ES
    *   **ArgoCD App:** `clusters/dev/apps/25-efk-stack.yaml`

### Phase 4: 로그 포맷팅 최적화 (FastAPI)
*   **목표:** 구조화된 로깅 (Structured Logging)
*   **작업 내용:**
    *   FastAPI의 기본 텍스트 로그를 JSON 포맷으로 변경 (`python-json-logger` 도입).
    *   **Why?** Fluent Bit가 JSON을 파싱하여 ES에 필드별로 인덱싱하면, "특정 에러 코드"나 "사용자 ID"로 검색하기가 매우 쉬워짐.

## 4. 리소스 요구사항 및 비용
*   **Elasticsearch:** 메모리 먹는 하마. 최소 4GB 힙 권장. (시스템 전체 8GB 필요)
*   **스토리지:** 로그 보관 주기에 따라 EBS 볼륨 크기 산정 필요 (초기 50GB 시작).
*   **비용:** `t3.large` 추가에 따른 AWS 비용 증가 예상 (약 $60/월).
    *   *비용 절감 팁:* 개발 단계에서는 Spot Instance 활용 고려.

## 5. 기대 효과
1.  **중앙 집중화:** 14개 노드에 흩어진 로그를 한 곳에서 조회.
2.  **연관 분석:** Trace ID(Jaeger)를 로그에 포함시켜 트레이싱과 로깅을 완벽하게 연결.
3.  **대시보드:** Kibana를 통해 "API 에러율", "응답 시간 분포" 등을 시각화.

## 6. 트러블슈팅 참조

### [CRI Parser 설정 문제](../troubleshooting/2025-12-18-fluent-bit-cri-parser.md)
**containerd 런타임 환경에서 로그 파싱 실패**

| 증상 | 원인 | 해결 |
|------|------|------|
| `log` 필드에 raw CRI 문자열 저장 | Docker parser로 CRI 형식 파싱 불가 | `cri` parser 적용 |
| `log_processed` 필드 null | JSON 병합 미동작 | `Merge_Log On` + `Merge_Log_Key` 설정 |

**핵심 교훈**: Kubernetes 클러스터의 Container Runtime(Docker vs containerd) 확인 필수.

```bash
# Container Runtime 확인
kubectl get nodes -o wide | awk '{print $1, $NF}'
```
