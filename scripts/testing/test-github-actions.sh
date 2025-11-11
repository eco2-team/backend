#!/bin/bash
# GitHub Actions 워크플로우 로컬 테스트 스크립트

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🧪 GitHub Actions Workflow Local Test"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 환경 변수 체크
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
check_env() {
    echo "1️⃣ 환경 변수 체크..."
    echo ""
    
    # AWS Credentials
    if [ -z "$AWS_ACCESS_KEY_ID" ]; then
        echo "❌ AWS_ACCESS_KEY_ID가 설정되지 않았습니다."
        echo "   export AWS_ACCESS_KEY_ID=AKIA..."
        exit 1
    else
        echo "✅ AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID:0:10}..."
    fi
    
    if [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
        echo "❌ AWS_SECRET_ACCESS_KEY가 설정되지 않았습니다."
        exit 1
    else
        echo "✅ AWS_SECRET_ACCESS_KEY: ********"
    fi
    
    # SSH Key
    if [ ! -f ~/.ssh/k8s-cluster-key.pem ]; then
        echo "❌ SSH Key가 없습니다: ~/.ssh/k8s-cluster-key.pem"
        exit 1
    else
        echo "✅ SSH Key: ~/.ssh/k8s-cluster-key.pem"
    fi
    
    echo ""
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Terraform 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
test_terraform() {
    echo "2️⃣ Terraform 검증..."
    echo ""
    
    cd terraform
    
    # Format Check
    echo "   🎨 Terraform Format Check..."
    if terraform fmt -check -recursive; then
        echo "   ✅ Format OK"
    else
        echo "   ⚠️  Format 문제 발견 (자동 수정 권장: terraform fmt -recursive)"
    fi
    
    # Init
    echo "   🚀 Terraform Init..."
    terraform init -backend=false  # 로컬 테스트는 backend 비활성화
    
    # Validate
    echo "   ✅ Terraform Validate..."
    terraform validate
    
    # Plan (Dry-run)
    echo "   📋 Terraform Plan..."
    terraform plan -out=/tmp/tfplan
    
    cd ..
    echo ""
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Ansible 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
test_ansible() {
    echo "3️⃣ Ansible 검증..."
    echo ""
    
    cd ansible
    
    # Ansible 설치 확인
    if ! command -v ansible &> /dev/null; then
        echo "❌ Ansible이 설치되지 않았습니다."
        echo "   pip install ansible"
        exit 1
    fi
    
    echo "   ✅ Ansible Version: $(ansible --version | head -n1)"
    
    # Syntax Check
    echo "   📝 Ansible Syntax Check..."
    ansible-playbook site.yml --syntax-check
    ansible-playbook playbooks/label-nodes.yml --syntax-check
    
    # Lint (yamllint 설치되어 있다면)
    if command -v yamllint &> /dev/null; then
        echo "   🔍 YAML Lint..."
        yamllint site.yml || echo "   ⚠️  Lint 경고 있음"
    fi
    
    cd ..
    echo ""
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GitHub Actions Workflow 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
test_workflow() {
    echo "4️⃣ GitHub Actions Workflow 검증..."
    echo ""
    
    # act 설치 확인 (GitHub Actions 로컬 실행 도구)
    if ! command -v act &> /dev/null; then
        echo "⚠️  'act'가 설치되지 않았습니다."
        echo "   설치: brew install act (macOS)"
        echo "   설치: https://github.com/nektos/act (기타)"
        echo ""
        echo "   Workflow YAML 문법만 체크합니다..."
        
        # YAML 문법만 체크
        if command -v yamllint &> /dev/null; then
            yamllint .github/workflows/infrastructure.yml
            echo "   ✅ Workflow YAML Syntax OK"
        fi
    else
        echo "   🎬 Act로 Workflow 테스트 (Dry-run)..."
        act -l -W .github/workflows/infrastructure.yml
    fi
    
    echo ""
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ArgoCD Application 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
test_argocd() {
    echo "5️⃣ ArgoCD Application 검증..."
    echo ""
    
    # kubectl 설치 확인
    if ! command -v kubectl &> /dev/null; then
        echo "⚠️  kubectl이 설치되지 않았습니다."
        echo "   건너뜁니다..."
        return
    fi
    
    # ArgoCD Application YAML 검증
    if [ -f argocd/application-14nodes.yaml ]; then
        echo "   📝 ArgoCD Application Dry-run..."
        kubectl apply -f argocd/application-14nodes.yaml --dry-run=client
        echo "   ✅ Application YAML Valid"
    fi
    
    echo ""
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 전체 테스트 실행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
main() {
    check_env
    test_terraform
    test_ansible
    test_workflow
    test_argocd
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✅ 모든 테스트 통과!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "🚀 다음 단계:"
    echo "   1. GitHub Secrets 설정 (AWS, SSH Key)"
    echo "   2. Git Push → PR 생성"
    echo "   3. GitHub Actions 자동 실행 확인"
    echo ""
}

# 스크립트 실행
main

