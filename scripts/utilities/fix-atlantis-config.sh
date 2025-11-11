#!/bin/bash
# Atlantis ConfigMap 수정 스크립트
# 올바른 Server-side Repo Config 형식으로 변경

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔧 Atlantis ConfigMap 수정 중..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 기존 ConfigMap 삭제
kubectl delete configmap atlantis-repo-config -n atlantis --ignore-not-found=true
echo "✅ 기존 ConfigMap 삭제 완료"

# 새로운 ConfigMap 생성
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: atlantis-repo-config
  namespace: atlantis
data:
  atlantis.yaml: |
    # Atlantis Server-side Repo Config
    # https://www.runatlantis.io/docs/server-side-repo-config.html
    
    # Repositories Configuration
    repos:
    - id: github.com/SeSACTHON/*
      workflow: infrastructure-workflow
      allowed_overrides:
        - workflow
        - apply_requirements
      allow_custom_workflows: true
      delete_source_branch_on_merge: true
    
    # Workflows Configuration
    workflows:
      infrastructure-workflow:
        plan:
          steps:
            - run: echo "🔍 Terraform Plan 시작..."
            - init
            - plan
        apply:
          steps:
            - run: echo "🚀 Terraform Apply 시작..."
            - apply
            - run: echo "✅ Terraform Apply 완료"
EOF

echo "✅ 새로운 ConfigMap 생성 완료"

# Atlantis Pod 재시작
echo ""
echo "🔄 Atlantis Pod 재시작 중..."
kubectl delete pod atlantis-0 -n atlantis --ignore-not-found=true

echo ""
echo "⏳ Pod 재시작 대기 중..."
sleep 10

# Pod 상태 확인
echo ""
echo "📊 Pod 상태 확인:"
kubectl get pods -n atlantis

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ ConfigMap 수정 완료"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📝 확인 명령어:"
echo "  kubectl logs -n atlantis atlantis-0"
echo "  kubectl describe pod -n atlantis atlantis-0"

