# 📚 [Docs] 아키텍처 분석 및 의사결정 문서

## 📋 변경 사항 요약

마이크로서비스 아키텍처 구축 과정에서의 분석 및 의사결정 문서를 추가했습니다.

### 주요 변경사항

#### 1. 배포 전략 분석 (16개 문서)
- Helm vs ArgoCD 비교 분석
- 네임스페이스 재구조화 분석
- Worker 노드 구성 분석
- AI 파이프라인 아키텍처 분석
- CDN 마이그레이션 분석

---

## 📚 문서 목록

### 🏗️ 인프라 & 배포 전략

#### 1. `ARGOCD_VS_HELM_COMPARISON.md`
- ArgoCD Application vs Helm Chart 비교
- 각 방식의 장단점 분석
- 권장 시나리오

#### 2. `HELM_UNIFIED_DEPLOYMENT_STRATEGY.md`
- 통합 Helm Chart 전략
- 단일 Chart로 전체 서비스 관리
- 확장성 및 유지보수성 분석

#### 3. `API_UNIFIED_HELM_STRUCTURE.md`
- API 서비스 Helm 구조
- `api/rest`와 `api/async` 분리
- Worker를 API 하위로 관리

#### 4. `DEPLOYMENT_REFLECTION_ANALYSIS.md`
- 현재 배포 구조 분석
- ArgoCD 자동 배포 검증
- 수동 배포 vs 자동 배포

#### 5. `MINIMAL_CHANGE_DEPLOYMENT_STRATEGY.md`
- 최소 변경 배포 전략
- 기존 구조 유지하며 개선
- 점진적 마이그레이션

---

### 🔧 네임스페이스 & 노드 구성

#### 6. `NAMESPACE_DOMAIN_STRUCTURE.md`
- 도메인 기반 네임스페이스 설계
- `api`, `workers`, `data`, `messaging` 분리
- 마이그레이션 계획

#### 7. `CORRECT_NAMESPACE_STRUCTURE.md`
- Sync/Async Worker 재정의
- Worker-1: Sync API
- Worker-2: Async Celery

#### 8. `NAMESPACE_REDESIGN_ANALYSIS.md`
- 8노드 클러스터 재설계
- API 노드 추가 제안
- 리소스 분배 최적화

#### 9. `WORKER_CLASSIFICATION_CORRECTION.md`
- Worker 분류 수정
- CPU vs Network 워크로드 재분석
- I/O 바운드 워크로드 재배치

#### 10. `WORKER_NODES_FINAL_CONFIGURATION.md`
- HPA 제거 후 Worker 노드 구성
- 고정 Replica로 안정성 확보
- 리소스 사용량 재계산

---

### 🤖 AI Pipeline & Worker

#### 11. `AI_PIPELINE_CORRECTION_GPT5.md`
- GPT-5 멀티모달 파이프라인
- Vision + Text 통합 처리
- GPT-4o mini 역할 재정의

#### 12. `FINAL_WORKER_NODE_LAYOUT.md`
- 최종 Worker 노드 레이아웃
- GPT-5 Analyzer, Response Generator
- Celery Beat 포함

#### 13. `FINAL_WORKER_LAYOUT_CLEAR_NAMING.md`
- Worker 이름 직관화
- `preprocess` → `image-uploader`
- `vision` → `gpt5-analyzer`
- `llm` → `response-generator`

#### 14. `CELERY_BEAT_DEPLOYMENT_PLAN.md`
- Celery Beat 배포 계획
- Worker-Network 노드 배치
- Single Replica + Recreate 전략

---

### 🌐 기타 분석

#### 15. `CDN_MIGRATION_ANALYSIS.md`
- S3 + CloudFront CDN 마이그레이션
- Pre-signed URL 보안 분석
- 비용 및 성능 비교

#### 16. `PULL_REQUEST_DOCS_MAIN.md`
- 문서 브랜치 PR 템플릿
- 변경사항 요약
- 주요 의사결정 기록

---

## 🎯 문서의 목적

### 1. 의사결정 투명성
- 왜 이 방식을 선택했는지 기록
- 대안 분석 및 비교
- 장단점 명확화

### 2. 지식 공유
- 팀원 온보딩 자료
- 아키텍처 이해도 향상
- 기술 부채 최소화

### 3. 향후 참조
- 비슷한 문제 발생 시 참고
- 개선 방향 설정
- 리팩토링 가이드

### 4. 변경 이력
- 아키텍처 진화 과정
- 시행착오 기록
- 학습 내용 정리

---

## 📊 주요 의사결정 요약

### 1. 배포 전략
- ✅ **선택**: Helm Chart + ArgoCD GitOps
- ❌ **제외**: 순수 ArgoCD Application
- **이유**: 환경 일관성, 재사용성, 확장성

### 2. 네임스페이스 구조
- ✅ **선택**: 도메인 기반 분리 (`api`, `workers`, `data`)
- ❌ **제외**: 단일 네임스페이스 (`default`)
- **이유**: 리소스 격리, 접근 제어, 모니터링 용이

### 3. Worker 분류
- ✅ **선택**: I/O vs Network 워크로드 분리
- ❌ **제외**: CPU vs Non-CPU 단순 분류
- **이유**: 실제 워크로드 특성에 맞는 최적화

### 4. AI Pipeline
- ✅ **선택**: GPT-5 멀티모달 (Vision + Text)
- ❌ **제외**: Vision 전용 모델 + LLM 조합
- **이유**: 모델 통합, 비용 절감, 응답 속도 향상

### 5. HPA 전략
- ✅ **선택**: Vision Worker만 HPA 제거
- ❌ **제외**: 모든 Worker에 HPA 적용
- **이유**: API Rate Limit, 안정성, 예측 가능성

### 6. 노드 확장
- ✅ **선택**: 13노드 (API 6 + Worker 2 + Infra 4 + Master 1)
- ❌ **제외**: 7노드 혼합 배치
- **이유**: 장애 격리, 독립 스케일링, 명확한 모니터링

---

## 🔧 활용 방법

### 1. 새 팀원 온보딩
```bash
# 아키텍처 이해
1. MICROSERVICES_ARCHITECTURE_13_NODES.md
2. HELM_UNIFIED_DEPLOYMENT_STRATEGY.md
3. AI_PIPELINE_CORRECTION_GPT5.md

# 배포 이해
4. HELM_ARGOCD_DEPLOY_GUIDE.md
5. DEVELOPMENT_READY.md
```

### 2. 의사결정 참조
```bash
# 비슷한 문제 발생 시
1. 관련 문서 검색
2. 대안 분석 섹션 확인
3. 선택 이유 파악
4. 현재 상황에 적용
```

### 3. 리팩토링 가이드
```bash
# 개선 필요 시
1. 현재 구조 분석 문서 확인
2. 개선 방향 검토
3. 새 분석 문서 작성
4. PR에 문서 포함
```

---

## ✅ 체크리스트

- [x] 16개 분석 문서 작성
- [x] 의사결정 과정 기록
- [x] 대안 분석 포함
- [x] 장단점 명확화
- [x] Mermaid 다이어그램 포함
- [x] 코드 예시 포함
- [ ] 팀원 리뷰 (PR 후)
- [ ] 문서 업데이트 (필요 시)

---

## 🔗 관련 PR

- #11 (feature/infra-13nodes)
- #12 (feature/helm-argocd-cicd)
- #13 (feature/microservices-skeleton)

---

## 👥 리뷰어

@backend-team @devops-team @tech-lead

---

## 📝 참고사항

- 이 문서들은 의사결정 과정을 기록한 것입니다
- 일부 문서는 시행착오 과정을 포함합니다
- 최종 선택과 다른 대안도 포함되어 있습니다
- 문서는 지속적으로 업데이트될 수 있습니다
- **문서 브랜치는 main에 직접 머지**합니다 (Git Flow 전략)

