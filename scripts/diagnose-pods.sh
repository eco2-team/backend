#!/bin/bash
# Pod 문제 진단 스크립트 (Master 노드에서 실행)

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 Pod 문제 진단"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Storage 노드 레이블 확인
echo "1️⃣ Storage 노드 레이블 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl get nodes -l workload=storage -o wide
echo ""

STORAGE_NODES=$(kubectl get nodes -l workload=storage --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$STORAGE_NODES" -eq 0 ]; then
    echo "❌ Storage 노드에 workload=storage 레이블이 없습니다!"
    echo ""
    echo "레이블 추가:"
    echo "  kubectl label nodes k8s-storage workload=storage --overwrite"
    echo ""
else
    echo "✅ Storage 노드 레이블 있음"
fi
echo ""

# 2. RabbitMQ Pod 상세 진단
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣ RabbitMQ Pod 진단"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl get pods -n messaging -l app.kubernetes.io/name=rabbitmq -o wide
echo ""

RABBITMQ_POD=$(kubectl get pods -n messaging -l app.kubernetes.io/name=rabbitmq -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ -n "$RABBITMQ_POD" ]; then
    echo "📋 Pod 이벤트:"
    kubectl describe pod "$RABBITMQ_POD" -n messaging | tail -50
    echo ""
    
    echo "📋 Init Container 로그:"
    kubectl logs "$RABBITMQ_POD" -n messaging --all-containers=true --tail=100 2>/dev/null || echo "로그 없음"
    echo ""
fi

# 3. RabbitMQ PVC 상태
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣ RabbitMQ PVC 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl get pvc -n messaging
echo ""

PENDING_PVC=$(kubectl get pvc -n messaging -o jsonpath='{.items[?(@.status.phase=="Pending")].metadata.name}' 2>/dev/null || echo "")
if [ -n "$PENDING_PVC" ]; then
    echo "⚠️  Pending PVC 발견: $PENDING_PVC"
    echo ""
    kubectl describe pvc "$PENDING_PVC" -n messaging | tail -30
    echo ""
fi

# 4. Redis Pod 진단
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣ Redis Pod 진단"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl get pods -l app=redis -n default -o wide
echo ""

REDIS_POD=$(kubectl get pods -l app=redis -n default -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ -n "$REDIS_POD" ]; then
    echo "📋 Pod 이벤트:"
    kubectl describe pod "$REDIS_POD" -n default | tail -50
    echo ""
    
    echo "📋 컨테이너 로그:"
    kubectl logs "$REDIS_POD" -n default --tail=50 2>/dev/null || echo "로그 없음"
    echo ""
fi

# 5. StorageClass 확인
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣ StorageClass 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl get storageclass
echo ""

GP3_SC=$(kubectl get storageclass gp3 -o jsonpath='{.metadata.name}' 2>/dev/null || echo "")
if [ -z "$GP3_SC" ]; then
    echo "❌ gp3 StorageClass가 없습니다!"
    echo ""
    echo "EBS CSI Driver 설치 확인:"
    echo "  kubectl get pods -n kube-system | grep ebs-csi"
    echo ""
fi

# 6. EBS CSI Driver 확인
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6️⃣ EBS CSI Driver 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl get pods -n kube-system | grep ebs-csi || echo "EBS CSI Driver Pod 없음"
echo ""

# 7. 노드 리소스 확인
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "7️⃣ Storage 노드 리소스"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl describe nodes -l workload=storage | grep -A 10 "Allocated resources" || echo "노드 정보 없음"
echo ""

# 8. 권장 해결 방법
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "💡 권장 해결 방법"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ "$STORAGE_NODES" -eq 0 ]; then
    echo "1. Storage 노드 레이블 추가:"
    echo "   kubectl label nodes k8s-storage workload=storage --overwrite"
    echo ""
fi

if [ -z "$GP3_SC" ]; then
    echo "2. StorageClass 생성 확인 (05-1-ebs-csi-driver.yml 재실행)"
    echo ""
fi

if [ -n "$PENDING_PVC" ]; then
    echo "3. PVC 바인딩 문제:"
    echo "   - EBS CSI Driver 상태 확인"
    echo "   - IAM 권한 확인 (ec2:CreateVolume)"
    echo ""
fi

echo "4. Pod 재시작 (문제 해결 후):"
echo "   kubectl delete pod $RABBITMQ_POD -n messaging"
echo "   kubectl delete pod $REDIS_POD -n default"
echo ""

