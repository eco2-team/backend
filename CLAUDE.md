# Claude Code Context

> Claude Code가 작업 시 참고하는 프로젝트 컨텍스트

---

## 프로젝트 개요

**Eco² (이코에코)**: 분리배출 도우미 AI 챗봇

- 폐기물 분류 및 환경 정보 제공
- LangGraph 기반 에이전트 파이프라인
- 마이크로서비스 아키텍처 (Kubernetes)

---

## 작업 대상 리포지토리

| 프로젝트 | 경로 | Git Remote | 스택 |
|---------|------|------------|------|
| **Backend** | `/Users/mango/workspace/SeSACTHON/backend` | `eco2-team/backend.git` | Python, FastAPI, LangGraph, gRPC, RabbitMQ |
| **Frontend** | `/Users/mango/workspace/SeSACTHON/frontend` | TBD | Vite + React + TypeScript |
| **Resume** | `/Users/mango/workspace/resume` | `mangowhoiscloud/resume.git` | 정적 HTML (GitHub Pages) |

---

## 외부 참조 (Knowledge Base)

블로그에서 지속적으로 작업 진행 상황 기록:

- **메인**: https://rooftopsnow.tistory.com/category/이코에코(Eco²)
- **Knowledge Base**: https://rooftopsnow.tistory.com/category/이코에코(Eco²) Knowledge Base

### Knowledge Base 구조 (66개 글)

| 섹션 | 수량 | 내용 |
|------|-----|------|
| Plans | 4 | 아키텍처 의사결정 |
| Foundations | 21 | 이론 및 논문 분석 |
| Applied | 10 | 실제 구현 |
| Reports | 11 | 기술 검증 리포트 |
| Logs | 2 | 운영 기록 |
| Troubleshooting | 12 | 문제 해결 |
| Python | 6 | 언어별 가이드 |

---

## 최근 기술 작업 (2026-01)

### 1. Chat Worker 리팩토링
- Feature-First → Layer-First (Clean Architecture)
- LangGraph + Port/Adapter 패턴 적용
- 현재 브랜치: `refactor/reward-fanout-exchange`

### 2. Intent 분류 시스템
- Multi-Intent 처리 (Chain-of-Intent)
- In-Context Learning 기반 응답 생성
- 프롬프트 분리 (Global + Local)

### 3. RAG 품질 평가
- LLM-as-a-Judge 전략
- Faithfulness, Groundedness, Context Relevance 지표
- Feedback Loop + Fallback Chain

### 4. 서브에이전트 추가
- Web Search Agent
- Vision Agent (이미지 기반 폐기물 분류)
- Character/Location Agent

---

## Backend 아키텍처

```
apps/
├── auth/              # 인증 서비스 (OAuth, JWT)
├── auth_relay/        # 인증 릴레이
├── auth_worker/       # 인증 비동기 처리
├── character/         # 캐릭터 서비스 (gRPC)
├── character_worker/  # 캐릭터 비동기 처리
├── chat/              # 채팅 API
├── chat_worker/       # 채팅 파이프라인 (LangGraph) ★ 주요 작업 영역
├── event_router/      # 이벤트 라우팅 (Redis Streams)
├── ext_authz/         # 외부 인가
├── images/            # 이미지 처리
├── location/          # 위치 기반 서비스
├── scan/              # 폐기물 스캔 API
├── scan_worker/       # 스캔 비동기 처리
├── sse_gateway/       # SSE 실시간 스트리밍
├── users/             # 사용자 서비스
└── users_worker/      # 사용자 비동기 처리

docs/
├── foundations/       # 기초 개념 문서 (27개+)
├── plans/             # 아키텍처 계획
├── reports/           # 기술 검증 리포트
├── blogs/             # 상세 기술 블로그
└── architecture/      # 아키텍처 다이어그램
```

---

## 인프라 환경

- **Kubernetes**: EKS 클러스터
- **Message Queue**: RabbitMQ (Celery)
- **Cache**: Redis Sentinel (3-node HA)
- **Database**: PostgreSQL
- **Observability**: Prometheus, Grafana, ELK
- **GitOps**: ArgoCD

---

## 작업 도구

- **Git CLI**: 브랜치 관리, PR 생성
- **SSH**: 클러스터 디버깅 (kubectl, stern)
- **docs/ harness**: 기술 문서 작성

---

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2026-01-15 | 최초 작성 (Claude Code 전환) |
