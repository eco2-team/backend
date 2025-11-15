#!/bin/bash

# PR 생성 스크립트
# 각 feature 브랜치를 push하고 gh CLI로 PR을 생성합니다.

set -e

echo "========================================="
echo "PR 생성 스크립트"
echo "========================================="

# 1. CI Quality Gate
echo -e "\n[1/6] CI Quality Gate 브랜치 push 및 PR 생성..."
git checkout feature/ci-quality-gate
git push -u origin feature/ci-quality-gate

gh pr create \
  --base develop \
  --title "ci: Add quality gate workflow for API services" \
  --body "## Summary
- API 서비스용 포괄적인 CI 파이프라인 추가
- Lint, Build, Test 단계를 포함한 품질 게이트 구현
- 여러 서비스에 대한 매트릭스 전략 지원
- GitHub Actions를 통한 자동화된 코드 품질 검증

## Changes
- ✨ 새로운 \`ci-quality-gate.yml\` 워크플로우 추가
- 📝 CI Quality Gate 아키텍처 문서 추가
- 🗑️ 오래된 infrastructure 워크플로우 백업 파일 제거

## Testing
- Not run (CI 파이프라인은 PR merge 후 자동 실행됨)

## Notes
- 각 API 서비스별로 독립적인 빌드 및 테스트 수행
- Flake8, Black을 통한 코드 스타일 검증
- pytest를 통한 단위 테스트 실행"

# 2. Atlantis Helm
echo -e "\n[2/6] Atlantis Helm 브랜치 push 및 PR 생성..."
git checkout feature/helm-atlantis
git push -u origin feature/helm-atlantis

gh pr create \
  --base develop \
  --title "feat: Migrate Atlantis to Helm chart deployment" \
  --body "## Summary
- Atlantis를 Helm Chart 기반 배포로 전환
- ArgoCD를 통한 GitOps 관리 구현
- Terraform 워크플로우 개선

## Changes
- 📦 Atlantis용 Helm Chart 생성 (templates, values)
- 🔄 ArgoCD Application 추가 (20-platform.yaml)
- 🔧 Ansible playbook을 Helm 설치 방식으로 업데이트
- 📝 Terraform 워크플로우 문서화
- 🗑️ 레거시 k8s manifest 제거

## Testing
- Not run (배포 후 Atlantis 웹 UI 및 Terraform plan/apply 테스트 필요)

## Notes
- Helm values에서 GitHub webhook secret, repo config 등 설정 필요
- ArgoCD를 통한 자동 배포 활성화됨"

# 3. ArgoCD App-of-Apps
echo -e "\n[3/6] ArgoCD App-of-Apps 브랜치 push 및 PR 생성..."
git checkout feature/argocd-app-of-apps
git push -u origin feature/argocd-app-of-apps

gh pr create \
  --base develop \
  --title "refactor: Migrate to ArgoCD App-of-Apps pattern" \
  --body "## Summary
- ArgoCD App-of-Apps 패턴으로 GitOps 구조 개선
- 계층화된 애플리케이션 관리 체계 구축
- 레거시 ApplicationSet 정리

## Changes
- 🏗️ App-of-Apps 패턴 구현
  - 00-foundations, 10-infrastructure, 20-platform
  - 30-monitoring, 40-data-operators, 50-data-clusters
  - 60-gitops-tools, 70-apis-app-of-apps
- 📦 개별 API 서비스 Application 분리
- 📝 GitOps 워크플로우 문서 개선
- 🗑️ 레거시 application manifest 아카이브

## Testing
- Not run (ArgoCD UI에서 애플리케이션 동기화 상태 확인 필요)

## Notes
- 각 레이어별 sync-wave를 통한 순차 배포
- API 서비스는 개별 Application으로 관리되어 독립 배포 가능"

# 4. FastAPI Services
echo -e "\n[4/6] FastAPI Services 브랜치 push 및 PR 생성..."
git checkout feature/fastapi-services
git push -u origin feature/fastapi-services

gh pr create \
  --base develop \
  --title "feat: Scaffold FastAPI services with domain-driven structure" \
  --body "## Summary
- 도메인 주도 설계(DDD) 기반 FastAPI 서비스 스캐폴딩
- 모든 서비스에 API 엔드포인트, 스키마, 서비스 레이어 추가
- GPT-4o-mini 기반 채팅 서비스 구현

## Changes
- 🎯 **Services Updated:**
  - \`auth\`: 인증/인가
  - \`character\`: 캐릭터 관리
  - \`chat\`: AI 채팅 (GPT-4o-mini 연동)
  - \`info\`: 정보 조회
  - \`location\`: 위치 기반 서비스
  - \`my\`: 사용자 프로필 관리
  - \`scan\`: QR/바코드 스캔

- 📂 **구조:**
  - \`app/api/v1/endpoints/\`: REST API 엔드포인트
  - \`app/schemas/\`: Pydantic 모델
  - \`app/services/\`: 비즈니스 로직
  - \`app/models/\`: 데이터베이스 모델
  - \`tests/\`: 단위 테스트

- 📝 FastAPI 엔드포인트 스타일 가이드 추가

## Testing
- Not run (각 서비스별 pytest 실행 필요)
- 테스트 명령: \`pytest services/<service>/tests -v\`

## Notes
- **중요**: Chat 서비스는 \`OPENAI_API_KEY\` 환경 변수 필요
- Health check: \`/health\`, Metrics: \`/metrics\` 엔드포인트 포함
- 모든 서비스는 Prometheus metrics 노출"

# 5. K8s Manifests Cleanup
echo -e "\n[5/6] K8s Manifests 브랜치 push 및 PR 생성..."
git checkout feature/k8s-manifests-cleanup
git push -u origin feature/k8s-manifests-cleanup

gh pr create \
  --base develop \
  --title "refactor: Modernize Kubernetes manifests structure" \
  --body "## Summary
- Kubernetes 매니페스트 구조 현대화
- Kustomize 패치 패턴 개선
- 레거시 리소스 정리

## Changes
- 🔧 Base 템플릿 개선 (deployment, service)
- 📦 Overlay 패치 구조 변경:
  - \`deployment-patch.yaml\` → \`patch-deployment.yaml\`
  - \`patch-service.yaml\` 추가
- 🏗️ Infrastructure 리소스 통합
- 🗑️ 레거시 모니터링 manifest 제거 (Helm으로 이전)
- 🗑️ Worker WAL deployments 제거
- 🌐 Network policy 및 Ingress 업데이트

## Testing
- Not run (kubectl apply --dry-run으로 검증 필요)
- 테스트 명령: \`kubectl kustomize k8s/overlays/<service>\`

## Notes
- 모니터링은 별도 Helm chart로 관리됨
- 각 서비스별 Kustomization 간소화
- ALB Controller egress policy 추가"

# 6. Docs Cleanup
echo -e "\n[6/6] Docs Cleanup 브랜치 push 및 PR 생성..."
git checkout feature/docs-cleanup
git push -u origin feature/docs-cleanup

gh pr create \
  --base develop \
  --title "docs: Reorganize documentation and archive legacy files" \
  --body "## Summary
- 문서 구조 재정리 및 아카이빙
- 아키텍처 결정 기록(ADR) 추가
- 레거시 파일 정리

## Changes
- 📁 **아카이브:**
  - WAL/Celery/RabbitMQ 설계 문서 → \`docs/architecture/design-reviews/\`
  - 오래된 PR 설명 → \`docs/pr_descriptions/\`
  
- 📝 **새로운 문서:**
  - \`ANSIBLE-TASK-CLASSIFICATION.md\`: Ansible 태스크 분류
  - \`OPERATOR-DESIGN-SPEC.md\`: Operator 설계 명세
  - \`USER-DATA-TO-OPERATOR-ANALYSIS.md\`: User-data 마이그레이션 분석
  - \`TERRAFORM-OPERATOR-PIPELINE.md\`: Terraform-Operator 파이프라인

- 🔢 Troubleshooting 문서 번호 체계 추가
- 🗑️ Charts 이미지 파일 제거 (적절한 위치로 이동)
- 🔧 개발 가이드 버전 업데이트 (03 → 02)

## Testing
- Not applicable (문서 변경)

## Notes
- 레거시 설계 문서는 참고용으로 보관
- 새로운 ADR은 현재 아키텍처 의사결정 반영"

echo -e "\n========================================="
echo "✅ 모든 PR 생성 완료!"
echo "========================================="
echo ""
echo "다음 단계:"
echo "1. GitHub에서 각 PR 확인"
echo "2. 리뷰어 지정"
echo "3. 순차적 머지 (CI → Helm → ArgoCD → FastAPI → K8s → Docs)"
echo ""
git checkout develop

