#!/bin/bash
# K8s 클러스터 전체 프로비저닝 자동화 스크립트

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"
ANSIBLE_DIR="$PROJECT_ROOT/ansible"

echo "🚀 Kubernetes 클러스터 프로비저닝 시작..."
echo "================================================"

# 1. Terraform 실행
echo ""
echo "📦 Step 1: Terraform - AWS 인프라 생성"
echo "================================================"
cd "$TERRAFORM_DIR"

if [ ! -d ".terraform" ]; then
    echo "Terraform 초기화 중..."
    terraform init
fi

echo "Terraform Plan 확인..."
terraform plan -out=tfplan

read -p "Terraform Apply를 실행하시겠습니까? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "❌ 취소되었습니다."
    exit 1
fi

echo "Terraform Apply 실행 중..."
terraform apply tfplan

echo "✅ AWS 인프라 생성 완료"

# 2. Ansible Inventory 자동 생성
echo ""
echo "📝 Step 2: Ansible Inventory 생성"
echo "================================================"
terraform -chdir="$TERRAFORM_DIR" output -raw ansible_inventory > "$ANSIBLE_DIR/inventory/hosts.ini"
echo "✅ Inventory 생성 완료: $ANSIBLE_DIR/inventory/hosts.ini"

# 3. EC2 부팅 대기
echo ""
echo "⏳ Step 3: EC2 인스턴스 부팅 대기 (120초)..."
echo "================================================"
sleep 120

# 4. Ansible 실행
echo ""
echo "🤖 Step 4: Ansible - Kubernetes 설치 및 설정"
echo "================================================"
cd "$ANSIBLE_DIR"

# 연결 테스트
echo "연결 테스트 중..."
ansible all -i inventory/hosts.ini -m ping || {
    echo "⚠️  연결 실패. 30초 더 대기..."
    sleep 30
    ansible all -i inventory/hosts.ini -m ping
}

echo "Ansible Playbook 실행 중..."
ansible-playbook -i inventory/hosts.ini site.yml

echo ""
echo "✅ Kubernetes 클러스터 구축 완료!"
echo "================================================"

# 5. 클러스터 정보 출력
echo ""
echo "📊 클러스터 정보"
echo "================================================"
terraform -chdir="$TERRAFORM_DIR" output cluster_info

echo ""
echo "🔐 SSH 접속 명령어"
echo "================================================"
terraform -chdir="$TERRAFORM_DIR" output ssh_commands

echo ""
echo "🎉 프로비저닝 완료!"
echo ""
echo "다음 단계:"
echo "1. SSH로 Master 접속"
echo "2. kubectl get nodes 확인"
echo "3. ArgoCD Applications 등록: kubectl apply -f argocd/applications/all-services.yaml"
echo "4. ArgoCD UI 접속: kubectl port-forward svc/argocd-server -n argocd 8080:443"

