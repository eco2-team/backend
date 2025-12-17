# Kibana 대시보드 (선언적 관리)

> **eck-custom-resources** 오퍼레이터를 통한 Kubernetes CRD 기반 선언적 관리

## 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                         GitOps Flow                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Git Repository              ArgoCD              Kubernetes     │
│   ┌───────────┐              ┌──────┐            ┌──────────┐   │
│   │ dashboard │   sync       │      │   apply    │ Dashboard│   │
│   │   .yaml   │ ──────────►  │      │ ─────────► │   CRD    │   │
│   └───────────┘              └──────┘            └────┬─────┘   │
│                                                       │         │
│                              eck-custom-resources     │         │
│                              ┌───────────────────┐    │         │
│                              │    Operator       │◄───┘         │
│                              └─────────┬─────────┘              │
│                                        │                        │
│                                        ▼                        │
│                              ┌───────────────────┐              │
│                              │     Kibana        │              │
│                              │   (Saved Objects) │              │
│                              └───────────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

## 파일 구조

```
workloads/logging/dashboards/
├── kustomization.yaml       # Kustomize 설정
├── dataview.yaml            # Data View (Index Pattern)
├── overview-dashboard.yaml  # [Logs ECO2] Overview
├── debug-dashboard.yaml     # [Logs ECO2] Developer Debug
└── business-dashboard.yaml  # [Logs ECO2] Business Metrics
```

## CRD 종류

| Kind | 설명 |
|------|------|
| `DataView` | Index Pattern (logs-app-*) |
| `Dashboard` | Kibana 대시보드 |
| `Visualization` | 개별 시각화 (필요시) |
| `SavedSearch` | 저장된 검색 (필요시) |

## 대시보드 목록

### 1. [Logs ECO2] Overview

**용도**: SRE/운영팀 - Golden Signals 모니터링

**패널**:
- Navigation Links (Markdown)
- Traffic Volume (Line Chart) - Golden Signal: Traffic
- Error Trend (Line Chart) - Golden Signal: Errors
- Service Health (Donut Chart)
- Log Level Distribution (Donut Chart)

### 2. [Logs ECO2] Developer Debug

**용도**: 개발자 - 디버깅 및 Trace 분석

**패널**:
- Navigation Links
- Errors by Type (Donut Chart)
- Errors by Service (Bar Chart)
- Error Details Table (with trace.id)
- Trace Correlation Search

### 3. [Logs ECO2] Business Metrics

**용도**: 비즈니스 - 사용자 활동 및 기능 사용량

**패널**:
- Navigation Links
- Total Logins (Metric)
- Rewards Granted (Metric)
- Rewards by Character (Donut Chart)
- Daily Logins by Provider (Line Chart)
- Feature Usage (Stacked Bar)

## 사용법

### 배포

```bash
# Kustomize로 배포
kubectl apply -k workloads/logging/dashboards/

# 또는 개별 파일
kubectl apply -f workloads/logging/dashboards/dataview.yaml
kubectl apply -f workloads/logging/dashboards/overview-dashboard.yaml
```

### 상태 확인

```bash
# Dashboard CRD 상태
kubectl get dashboards -n logging

# 상세 정보
kubectl describe dashboard logs-eco2-overview -n logging
```

### 삭제

```bash
kubectl delete -k workloads/logging/dashboards/
```

## 의존성

### 필수 컴포넌트

1. **ECK Operator** - Elasticsearch/Kibana 관리
2. **eck-custom-resources Operator** - Saved Objects CRD 관리
3. **Kibana 인스턴스** - `eco2-kibana` (targetInstance)

### CRD 설치 확인

```bash
# CRD 존재 확인
kubectl get crd dashboards.kibana.eck.github.com
kubectl get crd dataviews.kibana.eck.github.com

# 오퍼레이터 상태
kubectl get pods -n eck-custom-resources
```

## 베스트 프랙티스

적용된 베스트 프랙티스:
- **Elastic 공식 명명 규칙**: `[Logs ECO2] <Name>`
- **Google SRE Golden Signals**: Traffic, Errors 우선 표시
- **CNCF OpenTelemetry**: trace.id 연계
- **GitOps**: CRD로 선언적 관리, ArgoCD 자동 동기화

## 참조

- [eck-custom-resources GitHub](https://github.com/xco-sk/eck-custom-resources)
- [Elastic Dashboard Guidelines](https://www.elastic.co/docs/extend/integrations/dashboard-guidelines)
- [베스트 프랙티스 문서](../../docs/guide/observability/DASHBOARD_BEST_PRACTICES.md)
