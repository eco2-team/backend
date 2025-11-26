#!/bin/bash
# ArgoCD CLI 로그인 및 전체 동기화

set -e

ENV=${1:-dev}

echo "🔐 ArgoCD 로그인 시작..."
echo ""

# ArgoCD 서버 주소 (환경에 맞게 수정)
ARGOCD_SERVER="argocd.growbin.app"  # 또는 실제 도메인

# 1. ArgoCD CLI 설치 확인
if ! command -v argocd &> /dev/null; then
    echo "❌ ArgoCD CLI가 설치되어 있지 않습니다."
    echo ""
    echo "설치 방법:"
    echo "  macOS:  brew install argocd"
    echo "  Linux:  curl -sSL -o /usr/local/bin/argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64"
    echo ""
    exit 1
fi

echo "✅ ArgoCD CLI 발견: $(argocd version --client --short 2>/dev/null || echo 'unknown')"
echo ""

# 2. 로그인 방법 선택
echo "🔐 로그인 방법을 선택하세요:"
echo "  1) Username/Password"
echo "  2) SSO (Single Sign-On)"
echo "  3) Token"
echo "  4) Kubectl context (추천)"
echo ""
read -p "선택 (1-4): " login_method

case $login_method in
    1)
        # Username/Password
        echo ""
        read -p "ArgoCD 서버 주소 [$ARGOCD_SERVER]: " input_server
        ARGOCD_SERVER=${input_server:-$ARGOCD_SERVER}

        read -p "Username [admin]: " username
        username=${username:-admin}

        read -sp "Password: " password
        echo ""

        argocd login $ARGOCD_SERVER \
            --username $username \
            --password $password \
            --insecure  # self-signed cert인 경우
        ;;
    2)
        # SSO
        echo ""
        read -p "ArgoCD 서버 주소 [$ARGOCD_SERVER]: " input_server
        ARGOCD_SERVER=${input_server:-$ARGOCD_SERVER}

        argocd login $ARGOCD_SERVER --sso --insecure
        ;;
    3)
        # Token
        echo ""
        read -p "ArgoCD 서버 주소 [$ARGOCD_SERVER]: " input_server
        ARGOCD_SERVER=${input_server:-$ARGOCD_SERVER}

        read -sp "Token: " token
        echo ""

        argocd login $ARGOCD_SERVER \
            --auth-token $token \
            --insecure
        ;;
    4)
        # Kubectl context (가장 간단)
        echo ""
        echo "현재 kubectl context 사용..."

        # Port-forward로 ArgoCD 서버 접근
        echo "🔌 Port-forward 시작..."
        kubectl port-forward svc/argocd-server -n argocd 8080:443 &
        PF_PID=$!
        sleep 3

        # 초기 admin 비밀번호 가져오기
        ARGOCD_PASSWORD=$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" 2>/dev/null | base64 -d)

        if [ -z "$ARGOCD_PASSWORD" ]; then
            echo "⚠️  초기 admin 비밀번호를 찾을 수 없습니다."
            echo "수동으로 입력해주세요."
            read -sp "Password: " ARGOCD_PASSWORD
            echo ""
        else
            echo "✅ 초기 admin 비밀번호 자동 획득"
        fi

        argocd login localhost:8080 \
            --username admin \
            --password $ARGOCD_PASSWORD \
            --insecure

        # Port-forward 종료
        kill $PF_PID 2>/dev/null || true
        ;;
    *)
        echo "❌ 잘못된 선택"
        exit 1
        ;;
esac

# 3. 로그인 확인
echo ""
echo "✅ 로그인 성공!"
echo ""
argocd account get-user-info

# 4. Applications 목록
echo ""
echo "📋 $ENV 환경의 Applications:"
argocd app list --selector env=$ENV

echo ""
read -p "전체 동기화를 시작하시겠습니까? (y/n): " confirm
if [ "$confirm" != "y" ]; then
    echo "취소됨"
    exit 0
fi

# 5. sync-wave 순서대로 동기화
APPS=(
    "${ENV}-crds"
    "${ENV}-namespaces"
    "${ENV}-rbac-storage"
    "${ENV}-network-policies"
    "${ENV}-secrets-operator"
    "${ENV}-secrets-cr"
    "${ENV}-alb-controller"
    "${ENV}-external-dns"
    "${ENV}-monitoring-operator"
    "${ENV}-grafana"
    "${ENV}-postgresql"
    "${ENV}-redis"
    "${ENV}-apis-appset"
    "${ENV}-ingress"
)

for app in "${APPS[@]}"; do
    echo ""
    echo "🔄 Syncing: $app"

    # Application 존재 확인
    if ! argocd app get $app &> /dev/null; then
        echo "⚠️  $app이 존재하지 않습니다. 건너뜀."
        continue
    fi

    # Sync 실행
    argocd app sync $app \
        --prune \
        --retry-limit 3 \
        --timeout 300

    # Health 대기
    argocd app wait $app \
        --health \
        --timeout 300 || {
        echo "⚠️  $app이 Healthy 상태가 되지 않았습니다."
        read -p "계속하시겠습니까? (y/n): " continue_sync
        if [ "$continue_sync" != "y" ]; then
            exit 1
        fi
    }

    echo "✅ $app 완료"
    sleep 2
done

echo ""
echo "🎉 전체 동기화 완료!"
echo ""
argocd app list --selector env=$ENV
