#!/bin/bash
# 완전 자동 재구축 - 14-Node Architecture (Phase 1&2) + v0.6.0
# Phase 1&2: 8 nodes (16 vCPU, 22GB RAM)
# 1. Terraform destroy (기존 인프라 삭제)
# 2. Terraform apply (Phase 1&2 인프라 구축)
# 3. Ansible playbook (Kubernetes 설치)
# 4. Monitoring Stack 배포 (Phase 4에서 활성화)
# 5. Worker 이미지 빌드 & 배포 (Phase 4에서 활성화)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 로그 설정
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/auto-rebuild-$(date +%Y%m%d-%H%M%S).log"

# 로그 함수
log() {
    echo "$@" | tee -a "$LOG_FILE"
}

# 모든 출력을 로그에 기록
exec > >(tee -a "$LOG_FILE") 2>&1

log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "📝 로그 파일: $LOG_FILE"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🤖 완전 자동 재구축 시작 (Phase 1&2 - 8 nodes)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "⚠️  확인 프롬프트 없이 자동 실행됩니다!"
echo ""
echo "📋 실행 순서:"
echo "   1️⃣  Terraform destroy (기존 인프라 삭제)"
echo "   2️⃣  Terraform apply (Phase 1&2 인프라 구축 - 8 nodes)"
echo "   3️⃣  Ansible playbook (Kubernetes 설치)"
echo "   4️⃣  Monitoring Stack 배포 (Phase 4에서 활성화)"
echo "   5️⃣  Worker 이미지 빌드 (Phase 4에서 활성화)"
echo "   6️⃣  Worker 배포 (Phase 4에서 활성화)"
echo ""
echo "📊 Phase 1&2 구성:"
echo "   - Master (t3.large, 8GB)"
echo "   - API Nodes: auth, my, scan, character, location (5 nodes)"
echo "   - Infrastructure: PostgreSQL, Redis (2 nodes)"
echo "   - Total: 8 nodes, 16 vCPU, 22GB RAM"
echo ""
echo "⏱️  예상 소요 시간: 40-50분"
echo ""

# 환경 변수 확인
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 환경 변수 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Docker 및 GHCR 인증 확인
if [ -z "$GITHUB_TOKEN" ] || [ -z "$GITHUB_USERNAME" ]; then
    echo "⚠️  경고: GITHUB_TOKEN 또는 GITHUB_USERNAME이 설정되지 않았습니다."
    echo "   Worker 이미지 빌드를 건너뛰고 진행합니다."
    echo ""
    SKIP_WORKER_BUILD=true
else
    SKIP_WORKER_BUILD=false
    echo "✅ GitHub 인증 정보 확인됨"
fi

# 버전 설정
VERSION=${VERSION:-v0.6.0}
echo "   Version: $VERSION"
echo ""

# 자동 모드 설정
export AUTO_MODE=true

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 1: Terraform Destroy (destroy-with-cleanup.sh 호출)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣ Terraform Destroy - 기존 인프라 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# destroy-with-cleanup.sh 실행
if [ -f "$PROJECT_ROOT/scripts/maintenance/destroy-with-cleanup.sh" ]; then
    echo "🔧 destroy-with-cleanup.sh 실행 중..."
    echo ""
    
    export AUTO_MODE=true
    bash "$PROJECT_ROOT/scripts/maintenance/destroy-with-cleanup.sh"
    
    CLEANUP_EXIT_CODE=$?
    
    if [ $CLEANUP_EXIT_CODE -eq 0 ]; then
        echo ""
        echo "✅ 기존 인프라 삭제 완료"
    else
        echo ""
        echo "⚠️  destroy-with-cleanup.sh 실패 (exit code: $CLEANUP_EXIT_CODE)"
        echo "   일부 리소스가 남아있을 수 있습니다."
        echo "   계속 진행합니다..."
    fi
else
    echo "⚠️  destroy-with-cleanup.sh를 찾을 수 없습니다."
    echo "   간단한 정리만 수행합니다."
    echo ""
    
    cd "$PROJECT_ROOT/terraform"
    
    echo "🔧 Terraform 초기화..."
    terraform init -migrate-state -upgrade
    echo ""
    
    # 기존 리소스 확인
    if terraform state list >/dev/null 2>&1; then
        RESOURCE_COUNT=$(terraform state list 2>/dev/null | wc -l | tr -d ' ')
        
        if [ "$RESOURCE_COUNT" -gt 0 ]; then
            echo "📊 현재 리소스 개수: $RESOURCE_COUNT"
            echo ""
            echo "🗑️  Terraform destroy 실행..."
            
            set +e
            terraform destroy -auto-approve
            set -e
            
            echo "⏳ AWS 리소스 완전 삭제 대기 (30초)..."
            sleep 30
        else
            echo "ℹ️  삭제할 기존 인프라가 없습니다."
        fi
    else
        echo "ℹ️  State 파일이 없습니다. 새로운 배포입니다."
    fi
fi

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 2: Terraform Apply (Phase 1&2 - 8 nodes)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣ Terraform Apply - Phase 1&2 인프라 구축 (8 nodes)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "📋 Phase 1&2 구성:"
echo "   - Control Plane: 1 (t3.large)"
echo "   - API Phase 1: 2 (auth, my - t3.micro)"
echo "   - API Phase 2: 3 (scan, character, location - t3.small/micro)"
echo "   - Infrastructure: 2 (PostgreSQL, Redis - t3.medium/small)"
echo "   - 총 vCPU: 16 (한도 16 내)"
echo "   - 총 메모리: 22GB"
echo ""

cd "$PROJECT_ROOT/terraform"

echo "🔧 Terraform 초기화 (재확인)..."
terraform init -migrate-state -upgrade
echo ""

echo "🚀 Terraform apply 실행..."
echo "⚠️  CloudFront 생성으로 인해 10-15분 소요될 수 있습니다..."
echo ""

terraform apply -auto-approve

if [ $? -ne 0 ]; then
    echo "❌ Terraform apply 실패!"
    echo "로그 확인: $LOG_FILE"
    exit 1
fi

echo "✅ 13-Node 인프라 생성 완료"
echo ""

# 인스턴스 정보 출력
echo "📋 생성된 인스턴스 정보:"
terraform output -json | jq -r '
  "Master: " + (.master_public_ip.value // "N/A"),
  "API Nodes: " + ((.api_nodes_public_ips.value // []) | length | tostring) + " nodes",
  "Worker Nodes: " + ((.worker_nodes_public_ips.value // []) | length | tostring) + " nodes",
  "Infrastructure Nodes: " + ((.infra_nodes_public_ips.value // []) | length | tostring) + " nodes"
' 2>/dev/null || echo "  (인스턴스 정보 확인 중...)"
echo ""

# Master IP 저장 (나중에 사용)
MASTER_IP=$(terraform output -raw master_public_ip 2>/dev/null || echo "")
VPC_ID=$(terraform output -raw vpc_id 2>/dev/null || echo "")
ACM_ARN=$(terraform output -raw acm_certificate_arn 2>/dev/null || echo "")

echo "  Master IP: $MASTER_IP"
echo "  VPC ID: $VPC_ID"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 2.5: SSM Agent 등록 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2.5️⃣ SSM Agent 등록 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "⏳ SSM Agent 등록 대기 중..."
echo "   (인스턴스 생성 후 약 3-5분 소요)"
echo ""

MAX_WAIT=300  # 최대 5분
ELAPSED=0
EXPECTED_NODES=8  # Phase 1&2: 8 nodes

while [ $ELAPSED -lt $MAX_WAIT ]; do
    REGISTERED=$(aws ssm describe-instance-information \
        --region ap-northeast-2 \
        --filters "Key=tag:Name,Values=k8s-*" \
        --query 'length(InstanceInformationList[?PingStatus==`Online`])' \
        --output text 2>/dev/null || echo "0")
    
    if [ "$REGISTERED" -ge "$EXPECTED_NODES" ]; then
        echo "✅ 모든 노드 SSM 등록 완료 ($REGISTERED/$EXPECTED_NODES)"
        break
    fi
    
    echo "   ⏳ SSM 등록 진행 중... ($REGISTERED/$EXPECTED_NODES 노드) - ${ELAPSED}초 경과"
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done

if [ "$REGISTERED" -lt "$EXPECTED_NODES" ]; then
    echo ""
    echo "⚠️  일부 노드만 SSM 등록됨 ($REGISTERED/$EXPECTED_NODES)"
    echo "   계속 진행하시겠습니까? (y/n)"
    read -r CONTINUE
    if [ "$CONTINUE" != "y" ]; then
        echo "❌ 사용자가 중단했습니다."
        exit 1
    fi
fi

echo ""
echo "✅ SSM 준비 완료 - Ansible 실행 가능"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 3: Ansible Playbook
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣ Ansible Playbook - Kubernetes 설치"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Ansible 실행 (terraform/hosts 사용 - SSM 방식)
cd "$PROJECT_ROOT/ansible"

echo "🚀 Ansible playbook 실행 (SSM 방식)..."
ansible-playbook -i ../terraform/hosts site.yml \
    -e "vpc_id=$VPC_ID" \
    -e "acm_certificate_arn=$ACM_ARN"

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Ansible playbook 실패!"
    echo ""
    echo "디버깅 명령어:"
    echo "  ssh ubuntu@$MASTER_IP"
    echo "  kubectl get nodes"
    echo "  kubectl get pods -A"
    exit 1
fi

echo "✅ Kubernetes 설치 완료"
echo ""

# 클러스터 상태 확인 대기
echo "⏳ 클러스터 초기화 대기 (60초)..."
sleep 60
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 4: Monitoring Stack 배포 (원격)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣ Monitoring Stack 배포 (Prometheus/Grafana)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ -z "$MASTER_IP" ]; then
    echo "❌ Master IP를 찾을 수 없습니다. 모니터링 배포를 건너뜁니다."
else
    echo "📦 모니터링 파일 복사 중..."
    
    # k8s/monitoring 디렉토리 복사
    scp -r "$PROJECT_ROOT/k8s/monitoring" ubuntu@$MASTER_IP:~/
    
    # deploy-monitoring.sh 복사
    scp "$PROJECT_ROOT/scripts/deployment/deploy-monitoring.sh" ubuntu@$MASTER_IP:~/
    
    echo "✅ 파일 복사 완료"
    echo ""
    
    echo "🚀 원격으로 모니터링 배포 실행..."
    ssh ubuntu@$MASTER_IP << 'ENDSSH'
        # Node Exporter 배포
        echo "📊 Node Exporter 배포..."
        kubectl apply -f ~/monitoring/node-exporter.yaml
        
        # Prometheus Rules ConfigMap 생성
        echo "📊 Prometheus Rules 생성..."
        kubectl create configmap prometheus-rules \
            --from-file=~/monitoring/prometheus-rules.yaml \
            --namespace=default \
            --dry-run=client -o yaml | kubectl apply -f -
        
        # Prometheus 배포
        echo "📊 Prometheus 배포..."
        kubectl apply -f ~/monitoring/prometheus-deployment.yaml
        
        # Grafana Dashboards ConfigMap 생성
        echo "📊 Grafana Dashboards 생성..."
        kubectl create configmap grafana-dashboards \
            --from-file=~/monitoring/grafana-dashboard-13nodes.json \
            --namespace=default \
            --dry-run=client -o yaml | kubectl apply -f -
        
        # Grafana 배포
        echo "📊 Grafana 배포..."
        kubectl apply -f ~/monitoring/grafana-deployment.yaml
        
        echo ""
        echo "✅ 모니터링 스택 배포 완료"
        
        # 상태 확인
        echo ""
        echo "📊 배포 상태:"
        kubectl get pods -l component=monitoring
ENDSSH
    
    if [ $? -eq 0 ]; then
        echo "✅ 모니터링 배포 성공"
    else
        echo "⚠️  모니터링 배포 실패 (계속 진행)"
    fi
fi

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 5: Worker 이미지 빌드 (로컬)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣ Worker 이미지 빌드 (로컬)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$PROJECT_ROOT"

if [ "$SKIP_WORKER_BUILD" = true ]; then
    echo "⚠️  GitHub 인증 정보가 없어 Worker 빌드를 건너뜁니다."
    echo ""
    echo "수동으로 실행하려면:"
    echo "  export GITHUB_TOKEN=<your-token>"
    echo "  export GITHUB_USERNAME=<your-username>"
    echo "  export VERSION=$VERSION"
    echo "  ./scripts/deployment/build-workers.sh"
    echo ""
else
    echo "🐳 GHCR 로그인..."
    echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$GITHUB_USERNAME" --password-stdin
    
    if [ $? -ne 0 ]; then
        echo "❌ GHCR 로그인 실패. Worker 빌드를 건너뜁니다."
        SKIP_WORKER_BUILD=true
    else
        echo "✅ GHCR 로그인 성공"
        echo ""
        
        echo "🔨 Worker 이미지 빌드..."
        export VERSION=$VERSION
        ./scripts/deployment/build-workers.sh
        
        if [ $? -eq 0 ]; then
            echo "✅ Worker 이미지 빌드 및 푸시 완료"
        else
            echo "❌ Worker 이미지 빌드 실패"
            SKIP_WORKER_BUILD=true
        fi
    fi
fi

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 6: Worker 배포 (원격)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6️⃣ Worker 배포 (원격)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ "$SKIP_WORKER_BUILD" = true ]; then
    echo "⚠️  Worker 이미지가 빌드되지 않아 배포를 건너뜁니다."
    echo ""
elif [ -z "$MASTER_IP" ]; then
    echo "❌ Master IP를 찾을 수 없습니다. Worker 배포를 건너뜁니다."
else
    echo "📦 Worker 설정 파일 복사 중..."
    
    # k8s/workers 디렉토리 복사
    scp -r "$PROJECT_ROOT/k8s/workers" ubuntu@$MASTER_IP:~/
    
    echo "✅ 파일 복사 완료"
    echo ""
    
    echo "🚀 원격으로 Worker 배포 실행..."
    ssh ubuntu@$MASTER_IP << ENDSSH
        # Worker 배포
        echo "📦 Worker 배포..."
        kubectl apply -f ~/workers/worker-wal-deployments.yaml
        
        echo ""
        echo "✅ Worker 배포 완료"
        
        # 상태 확인
        echo ""
        echo "📊 배포 상태:"
        kubectl get pods -l component=worker
        kubectl get pvc -l component=wal
ENDSSH
    
    if [ $? -eq 0 ]; then
        echo "✅ Worker 배포 성공"
    else
        echo "⚠️  Worker 배포 실패"
    fi
fi

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 완료 요약
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 자동 재구축 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "📊 배포 결과:"
echo "  ✅ 13-Node Kubernetes 클러스터"
echo "  ✅ Prometheus/Grafana 모니터링"
if [ "$SKIP_WORKER_BUILD" = false ]; then
    echo "  ✅ Storage/AI Workers with WAL"
else
    echo "  ⚠️  Workers (수동 배포 필요)"
fi
echo ""

echo "🔍 클러스터 확인:"
if [ -n "$MASTER_IP" ]; then
    echo "  ssh ubuntu@$MASTER_IP"
    echo "  kubectl get nodes -o wide"
    echo "  kubectl get pods -A"
    echo ""
    echo "📊 모니터링 접속:"
    echo "  Prometheus: kubectl port-forward svc/prometheus 9090:9090"
    echo "  Grafana: kubectl port-forward svc/grafana 3000:3000"
    echo ""
    echo "Grafana 비밀번호 확인:"
    echo "  kubectl get secret grafana-admin -o jsonpath='{.data.password}' | base64 -d"
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
