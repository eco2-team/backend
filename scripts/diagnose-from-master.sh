#!/bin/bash
# Master 노드에서 직접 실행할 진단 명령어 모음
# Master 노드에 SSH 접속 후 실행

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 Pod 문제 진단 (Master 노드)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Storage 노드 레이블 확인
echo "1️⃣ Storage 노드 레이블 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl get nodes -l workload=storage -o wide
echo ""
kubectl get nodes --show-labels | grep storage
echo ""

# 2. RabbitMQ Pod 상태
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣ RabbitMQ Pod 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl get pods -n messaging -o wide
echo ""

# 3. RabbitMQ Pod 상세 정보
RABBITMQ_POD=$(kubectl get pods -n messaging -l app.kubernetes.io/name=rabbitmq -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [ -n "$RABBITMQ_POD" ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "3️⃣ RabbitMQ Pod 이벤트 (상위 30줄)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    kubectl describe pod "$RABBITMQ_POD" -n messaging | tail -30
    echo ""
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "4️⃣ RabbitMQ Init Container 로그"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    # Init Container 이름 확인
    INIT_CONTAINERS=$(kubectl get pod "$RABBITMQ_POD" -n messaging -o jsonpath='{.spec.initContainers[*].name}' 2>/dev/null || echo "")
    if [ -n "$INIT_CONTAINERS" ]; then
        echo "Init Containers: $INIT_CONTAINERS"
        for init in $INIT_CONTAINERS; do
            echo ""
            echo "--- $init 로그 ---"
            kubectl logs "$RABBITMQ_POD" -n messaging -c "$init" --tail=100 2>/dev/null || echo "로그 없음"
        done
    else
        echo "전체 컨테이너 로그:"
        kubectl logs "$RABBITMQ_POD" -n messaging --all-containers=true --tail=100 2>/dev/null || echo "로그 없음"
    fi
    echo ""
fi

# 5. RabbitMQ PVC 상태
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣ RabbitMQ PVC 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl get pvc -n messaging
echo ""

PENDING_PVC=$(kubectl get pvc -n messaging -o jsonpath='{.items[?(@.status.phase=="Pending")].metadata.name}' 2>/dev/null || echo "")
if [ -n "$PENDING_PVC" ]; then
    echo "⚠️  Pending PVC: $PENDING_PVC"
    kubectl describe pvc "$PENDING_PVC" -n messaging | tail -30
    echo ""
fi

# 6. Redis Pod 상태
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6️⃣ Redis Pod 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl get pods -l app=redis -n default -o wide
echo ""

REDIS_POD=$(kubectl get pods -l app=redis -n default -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ -n "$REDIS_POD" ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "7️⃣ Redis Pod 이벤트 및 로그"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    kubectl describe pod "$REDIS_POD" -n default | tail -30
    echo ""
    echo "--- Redis 로그 ---"
    kubectl logs "$REDIS_POD" -n default --tail=50 2>/dev/null || echo "로그 없음"
    echo ""
fi

# 8. StorageClass 및 EBS CSI
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "8️⃣ StorageClass 및 EBS CSI Driver"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl get storageclass
echo ""
kubectl get pods -n kube-system | grep ebs-csi || echo "EBS CSI Driver Pod 없음"
echo ""

# 9. 노드 리소스 확인
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "9️⃣ Storage 노드 리소스"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl describe nodes k8s-storage | grep -A 10 "Allocated resources" || echo "노드 정보 없음"
echo ""

# 10. 권장 해결 방법
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "💡 다음 단계"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "위의 출력을 확인하여 문제 원인을 파악하세요."
echo ""
echo "일반적인 문제:"
echo "  1. PVC Pending → StorageClass 또는 EBS CSI Driver 문제"
echo "  2. Init Container 실패 → 이미지 Pull 또는 권한 문제"
echo "  3. 노드 리소스 부족 → 다른 Pod 제거 또는 노드 추가"
echo ""

