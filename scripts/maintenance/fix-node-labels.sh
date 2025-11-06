#!/bin/bash
# 노드 레이블 확인 및 수정 스크립트
# PostgreSQL, RabbitMQ, Redis가 Storage 노드에 배포되도록 레이블 설정

set -e

MASTER_NODE=${1:-"master"}
MASTER_USER=${2:-"ubuntu"}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 노드 레이블 확인 및 수정"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Master 노드에서 실행
if [ -n "$MASTER_NODE" ]; then
    echo "📡 Master 노드 연결: $MASTER_USER@$MASTER_NODE"
    echo ""
    
    # 1. 현재 노드 레이블 확인
    echo "1️⃣ 현재 노드 레이블 확인"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ssh $MASTER_USER@$MASTER_NODE "kubectl get nodes --show-labels"
    echo ""
    
    # 2. workload 레이블 확인
    echo "2️⃣ workload 레이블 상세 확인"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ssh $MASTER_USER@$MASTER_NODE "kubectl get nodes -L workload,instance-type,role"
    echo ""
    
    # 3. 노드 레이블 수정 (site.yml에 정의된 대로)
    echo "3️⃣ 노드 레이블 적용"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Worker-1: Application
    echo "📌 k8s-worker-1 → workload=application"
    ssh $MASTER_USER@$MASTER_NODE "kubectl label nodes k8s-worker-1 workload=application instance-type=t3.medium role=application --overwrite" || true
    
    # Worker-2: Async Workers
    echo "📌 k8s-worker-2 → workload=async-workers"
    ssh $MASTER_USER@$MASTER_NODE "kubectl label nodes k8s-worker-2 workload=async-workers instance-type=t3.medium role=workers --overwrite" || true
    
    # Storage: Stateful Services
    echo "📌 k8s-storage → workload=storage"
    ssh $MASTER_USER@$MASTER_NODE "kubectl label nodes k8s-storage workload=storage instance-type=t3.large role=storage --overwrite" || true
    
    echo ""
    
    # 4. 레이블 적용 확인
    echo "4️⃣ 레이블 적용 확인"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    ssh $MASTER_USER@$MASTER_NODE "kubectl get nodes -L workload,instance-type,role"
    echo ""
    
    # 5. Storage 노드 확인
    echo "5️⃣ Storage 노드 확인"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    STORAGE_NODE=$(ssh $MASTER_USER@$MASTER_NODE "kubectl get nodes -l workload=storage -o name" | head -1)
    
    if [ -z "$STORAGE_NODE" ]; then
        echo "❌ workload=storage 레이블을 가진 노드가 없습니다!"
        echo ""
        echo "⚠️  수동 확인 필요:"
        echo "   kubectl get nodes"
        echo "   kubectl label nodes <NODE_NAME> workload=storage --overwrite"
        exit 1
    else
        echo "✅ Storage 노드 발견: $STORAGE_NODE"
    fi
    echo ""
    
    # 6. 실패한 Pod 재시작
    echo "6️⃣ 실패한 Pod 재시작"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # PostgreSQL
    echo "📦 PostgreSQL Pod 삭제 (재생성 유도)"
    ssh $MASTER_USER@$MASTER_NODE "kubectl delete pod -l app=postgres -n default --ignore-not-found=true" || true
    
    # RabbitMQ
    echo "📦 RabbitMQ Pod 삭제 (재생성 유도)"
    ssh $MASTER_USER@$MASTER_NODE "kubectl delete pod -l app.kubernetes.io/name=rabbitmq -n messaging --ignore-not-found=true" || true
    
    echo ""
    
    # 7. Pod 상태 확인
    echo "7️⃣ Pod 재생성 상태 확인 (30초 대기)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "⏳ 대기 중..."
    sleep 30
    
    echo ""
    echo "PostgreSQL:"
    ssh $MASTER_USER@$MASTER_NODE "kubectl get pods -l app=postgres -n default -o wide" || true
    
    echo ""
    echo "RabbitMQ:"
    ssh $MASTER_USER@$MASTER_NODE "kubectl get pods -l app.kubernetes.io/name=rabbitmq -n messaging -o wide" || true
    
    echo ""
    
else
    # 로컬 kubectl 사용
    echo "📡 로컬 kubectl 사용"
    echo ""
    
    echo "1️⃣ 현재 노드 레이블 확인"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    kubectl get nodes -L workload,instance-type,role
    echo ""
    
    echo "2️⃣ 노드 레이블 적용"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    kubectl label nodes k8s-worker-1 workload=application instance-type=t3.medium role=application --overwrite
    kubectl label nodes k8s-worker-2 workload=async-workers instance-type=t3.medium role=workers --overwrite
    kubectl label nodes k8s-storage workload=storage instance-type=t3.large role=storage --overwrite
    echo ""
    
    echo "3️⃣ 레이블 적용 확인"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    kubectl get nodes -L workload,instance-type,role
    echo ""
    
    echo "4️⃣ 실패한 Pod 재시작"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    kubectl delete pod -l app=postgres -n default --ignore-not-found=true
    kubectl delete pod -l app.kubernetes.io/name=rabbitmq -n messaging --ignore-not-found=true
    echo ""
    
    echo "⏳ 30초 대기..."
    sleep 30
    
    echo ""
    echo "5️⃣ Pod 재생성 상태 확인"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    kubectl get pods -l app=postgres -n default -o wide
    kubectl get pods -l app.kubernetes.io/name=rabbitmq -n messaging -o wide
    echo ""
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 노드 레이블 수정 완료"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "【최종 확인】"
echo "  kubectl get nodes -L workload"
echo "  kubectl get pods -n default -o wide"
echo "  kubectl get pods -n messaging -o wide"
echo ""

