#!/bin/bash
# PostgreSQL 원격 진단 스크립트
# Master 노드에 접속하여 PostgreSQL 상태를 종합적으로 진단

set -e

MASTER_IP=${1:-""}
SSH_USER=${2:-"ubuntu"}

if [ -z "$MASTER_IP" ]; then
    echo "사용법: $0 <MASTER_IP> [SSH_USER]"
    echo "예시: $0 52.79.238.50 ubuntu"
    exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 PostgreSQL 원격 진단"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Master 노드: $MASTER_IP"
echo "SSH 사용자: $SSH_USER"
echo ""

# 1. 기본 정보 수집
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣ 기본 정보 수집"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh $SSH_USER@$MASTER_IP << 'EOF'
echo "📋 Namespace 확인:"
kubectl get ns | grep -E "(NAME|default)"
echo ""

echo "📦 StatefulSet 확인:"
kubectl get statefulset -n default | grep -E "(NAME|postgres)" || echo "  ❌ PostgreSQL StatefulSet 없음"
echo ""

echo "🗂️ Pod 확인:"
kubectl get pods -n default -l app=postgres -o wide || echo "  ❌ PostgreSQL Pod 없음"
echo ""

echo "🔌 Service 확인:"
kubectl get svc -n default | grep -E "(NAME|postgres)" || echo "  ❌ PostgreSQL Service 없음"
echo ""

echo "🔐 Secret 확인:"
kubectl get secret -n default | grep -E "(NAME|postgres)" || echo "  ❌ PostgreSQL Secret 없음"
echo ""

echo "💾 PVC 확인:"
kubectl get pvc -n default | grep -E "(NAME|postgres)" || echo "  ❌ PostgreSQL PVC 없음"
echo ""
EOF

# 2. Pod 상태 상세 분석
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣ Pod 상태 상세 분석"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh $SSH_USER@$MASTER_IP << 'EOF'
POD_COUNT=$(kubectl get pods -n default -l app=postgres --no-headers 2>/dev/null | wc -l)

if [ "$POD_COUNT" -eq 0 ]; then
    echo "❌ PostgreSQL Pod가 없습니다."
    echo ""
    echo "StatefulSet 확인:"
    kubectl get statefulset -n default postgres 2>&1 || echo "  StatefulSet도 없습니다."
    echo ""
    echo "최근 이벤트:"
    kubectl get events -n default --sort-by='.lastTimestamp' | tail -20
    exit 0
fi

POD_NAME=$(kubectl get pods -n default -l app=postgres -o jsonpath='{.items[0].metadata.name}')
echo "Pod 이름: $POD_NAME"
echo ""

echo "📊 Pod 상태:"
kubectl get pod $POD_NAME -n default -o wide
echo ""

echo "🔍 Pod 상세 정보:"
kubectl describe pod $POD_NAME -n default | grep -A 30 "Conditions:"
echo ""

echo "📍 Node 배치 확인:"
NODE=$(kubectl get pod $POD_NAME -n default -o jsonpath='{.spec.nodeName}')
echo "  배치된 노드: $NODE"
kubectl get node $NODE -L workload,instance-type,role 2>/dev/null || echo "  노드 정보 조회 실패"
echo ""

echo "🔄 Restart 횟수:"
kubectl get pod $POD_NAME -n default -o jsonpath='{.status.containerStatuses[0].restartCount}'
echo ""
echo ""

echo "⚡ Pod Events (최근):"
kubectl describe pod $POD_NAME -n default | grep "Events:" -A 30 | tail -20
echo ""
EOF

# 3. 리소스 사용량
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣ 리소스 사용량"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh $SSH_USER@$MASTER_IP << 'EOF'
POD_NAME=$(kubectl get pods -n default -l app=postgres -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -z "$POD_NAME" ]; then
    echo "❌ Pod가 없어 리소스 확인 불가"
    exit 0
fi

echo "💻 CPU/Memory 사용량 (Pod):"
kubectl top pod $POD_NAME -n default 2>/dev/null || echo "  ⚠️ metrics-server 미설치 또는 데이터 없음"
echo ""

echo "📦 리소스 할당:"
kubectl get pod $POD_NAME -n default -o jsonpath='{.spec.containers[0].resources}' | python3 -m json.tool 2>/dev/null || echo "  정보 조회 실패"
echo ""
echo ""

NODE=$(kubectl get pod $POD_NAME -n default -o jsonpath='{.spec.nodeName}')
echo "🖥️ Node 리소스 사용량 ($NODE):"
kubectl top node $NODE 2>/dev/null || echo "  ⚠️ metrics-server 미설치 또는 데이터 없음"
echo ""

echo "📊 Node 리소스 할당 현황:"
kubectl describe node $NODE | grep -A 10 "Allocated resources:"
echo ""
EOF

# 4. Storage 상태
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣ Storage 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh $SSH_USER@$MASTER_IP << 'EOF'
echo "💾 PVC 상세 정보:"
kubectl get pvc -n default -l app=postgres -o wide 2>/dev/null || echo "  ❌ PVC 없음"
echo ""

PVC_NAME=$(kubectl get pvc -n default -l app=postgres -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$PVC_NAME" ]; then
    echo "PVC 이름: $PVC_NAME"
    echo ""
    kubectl describe pvc $PVC_NAME -n default | grep -E "(Name:|Namespace:|StorageClass:|Status:|Volume:|Capacity:|Access Modes:)"
    echo ""
fi

echo "📦 PV 정보:"
PV_NAME=$(kubectl get pvc -n default -l app=postgres -o jsonpath='{.items[0].spec.volumeName}' 2>/dev/null)
if [ -n "$PV_NAME" ]; then
    kubectl get pv $PV_NAME -o wide 2>/dev/null
    echo ""
fi
EOF

# 5. 연결 테스트
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣ 연결 테스트"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh $SSH_USER@$MASTER_IP << 'EOF'
POD_NAME=$(kubectl get pods -n default -l app=postgres -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -z "$POD_NAME" ]; then
    echo "❌ Pod가 없어 연결 테스트 불가"
    exit 0
fi

POD_STATUS=$(kubectl get pod $POD_NAME -n default -o jsonpath='{.status.phase}')
if [ "$POD_STATUS" != "Running" ]; then
    echo "❌ Pod 상태가 Running이 아님: $POD_STATUS"
    echo "   연결 테스트 건너뜀"
    exit 0
fi

echo "🔌 PostgreSQL 연결 테스트:"
kubectl exec -n default $POD_NAME -- psql -U admin -d sesacthon -c "SELECT version();" 2>&1 | head -5
if [ $? -eq 0 ]; then
    echo "  ✅ 연결 성공"
else
    echo "  ❌ 연결 실패"
fi
echo ""

echo "📊 데이터베이스 목록:"
kubectl exec -n default $POD_NAME -- psql -U admin -d sesacthon -c "\l" 2>&1 | head -10
echo ""

echo "🔗 Service DNS 테스트:"
kubectl run test-dns --image=busybox --rm -it --restart=Never -- nslookup postgres.default.svc.cluster.local 2>&1 | grep -A 5 "Name:"
echo ""
EOF

# 6. 로그 확인
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6️⃣ 로그 확인 (최근 50줄)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh $SSH_USER@$MASTER_IP << 'EOF'
POD_NAME=$(kubectl get pods -n default -l app=postgres -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -z "$POD_NAME" ]; then
    echo "❌ Pod가 없어 로그 확인 불가"
    exit 0
fi

echo "📜 PostgreSQL 로그:"
kubectl logs -n default $POD_NAME --tail=50 2>&1
echo ""

echo "📜 이전 로그 (재시작된 경우):"
kubectl logs -n default $POD_NAME --previous --tail=30 2>/dev/null || echo "  ℹ️  이전 로그 없음 (재시작 없음)"
echo ""
EOF

# 7. 문제 진단
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "7️⃣ 문제 진단"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh $SSH_USER@$MASTER_IP << 'EOF'
echo "🔍 일반적인 문제 확인:"
echo ""

# Pod 상태 확인
POD_COUNT=$(kubectl get pods -n default -l app=postgres --no-headers 2>/dev/null | wc -l)
if [ "$POD_COUNT" -eq 0 ]; then
    echo "❌ PostgreSQL Pod가 없습니다"
    echo "   → StatefulSet 확인 필요"
    echo "   → kubectl get statefulset -n default postgres"
    echo ""
fi

POD_NAME=$(kubectl get pods -n default -l app=postgres -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$POD_NAME" ]; then
    POD_STATUS=$(kubectl get pod $POD_NAME -n default -o jsonpath='{.status.phase}')
    
    if [ "$POD_STATUS" = "Pending" ]; then
        echo "⚠️ Pod가 Pending 상태입니다"
        echo "   가능한 원인:"
        echo "   1. NodeSelector 불일치"
        NODE_SELECTOR=$(kubectl get pod $POD_NAME -n default -o jsonpath='{.spec.nodeSelector}')
        echo "      NodeSelector: $NODE_SELECTOR"
        echo ""
        echo "   2. 리소스 부족"
        kubectl describe pod $POD_NAME -n default | grep -A 5 "Events:" | grep -i "insufficient\|failed"
        echo ""
        echo "   3. PVC Pending"
        kubectl get pvc -n default -l app=postgres
        echo ""
    elif [ "$POD_STATUS" = "CrashLoopBackOff" ] || [ "$POD_STATUS" = "Error" ]; then
        echo "❌ Pod가 $POD_STATUS 상태입니다"
        echo "   최근 로그:"
        kubectl logs -n default $POD_NAME --tail=20 2>&1 | tail -10
        echo ""
    elif [ "$POD_STATUS" = "Running" ]; then
        echo "✅ Pod가 Running 상태입니다"
        
        # 재시작 횟수 확인
        RESTART_COUNT=$(kubectl get pod $POD_NAME -n default -o jsonpath='{.status.containerStatuses[0].restartCount}')
        if [ "$RESTART_COUNT" -gt 0 ]; then
            echo "   ⚠️ 재시작 횟수: $RESTART_COUNT"
            echo "   → 로그 확인 필요"
        else
            echo "   재시작: 없음"
        fi
        echo ""
    fi
fi

# Storage 확인
PVC_COUNT=$(kubectl get pvc -n default -l app=postgres --no-headers 2>/dev/null | wc -l)
if [ "$PVC_COUNT" -eq 0 ]; then
    echo "⚠️ PVC가 없습니다"
    echo "   → StatefulSet volumeClaimTemplates 확인 필요"
    echo ""
else
    PVC_STATUS=$(kubectl get pvc -n default -l app=postgres -o jsonpath='{.items[0].status.phase}')
    if [ "$PVC_STATUS" != "Bound" ]; then
        echo "❌ PVC 상태가 Bound가 아님: $PVC_STATUS"
        echo "   → StorageClass 확인 필요"
        echo "   → kubectl get storageclass"
        echo ""
    fi
fi

# Secret 확인
if ! kubectl get secret postgres-secret -n default &>/dev/null; then
    echo "❌ postgres-secret이 없습니다"
    echo "   → Secret 생성 필요"
    echo ""
fi

# Node 레이블 확인
echo "🏷️ 노드 레이블 확인:"
kubectl get nodes -L workload --no-headers | while read line; do
    NODE_NAME=$(echo $line | awk '{print $1}')
    WORKLOAD=$(echo $line | awk '{print $6}')
    if [ "$WORKLOAD" = "storage" ]; then
        echo "  ✅ Storage 노드 발견: $NODE_NAME (workload=$WORKLOAD)"
    fi
done

STORAGE_NODE_COUNT=$(kubectl get nodes -L workload --no-headers | grep "storage" | wc -l)
if [ "$STORAGE_NODE_COUNT" -eq 0 ]; then
    echo "  ❌ workload=storage 레이블을 가진 노드가 없습니다"
    echo "     → 노드 레이블 적용 필요"
    echo "     → kubectl label nodes <NODE_NAME> workload=storage"
    echo ""
fi

EOF

# 8. 진단 요약
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "8️⃣ 진단 요약"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh $SSH_USER@$MASTER_IP << 'EOF'
POD_NAME=$(kubectl get pods -n default -l app=postgres -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -z "$POD_NAME" ]; then
    echo "🔴 상태: PostgreSQL이 배포되지 않음"
    echo ""
    echo "권장 조치:"
    echo "  1. Ansible 플레이북 실행"
    echo "     cd "$PROJECT_ROOT/ansible" && ansible-playbook -i inventory/hosts.ini site.yml --tags postgresql"
    echo ""
else
    POD_STATUS=$(kubectl get pod $POD_NAME -n default -o jsonpath='{.status.phase}')
    
    if [ "$POD_STATUS" = "Running" ]; then
        # 연결 테스트
        kubectl exec -n default $POD_NAME -- psql -U admin -d sesacthon -c "SELECT 1;" &>/dev/null
        if [ $? -eq 0 ]; then
            echo "🟢 상태: 정상 (Running & Connectable)"
            echo ""
            echo "ℹ️  PostgreSQL이 정상적으로 작동 중입니다."
            echo ""
            echo "연결 정보:"
            echo "  Host: postgres.default.svc.cluster.local"
            echo "  Port: 5432"
            echo "  Database: sesacthon"
            echo "  Username: admin"
        else
            echo "🟡 상태: Running이지만 연결 불가"
            echo ""
            echo "권장 조치:"
            echo "  1. 로그 확인"
            echo "     kubectl logs -n default $POD_NAME"
            echo "  2. Secret 확인"
            echo "     kubectl get secret postgres-secret -n default"
        fi
    elif [ "$POD_STATUS" = "Pending" ]; then
        echo "🟡 상태: Pending (스케줄링 대기)"
        echo ""
        echo "권장 조치:"
        echo "  1. 노드 레이블 확인 및 적용"
        echo "     bash scripts/diagnostics/fix-node-labels.sh $MASTER_IP ubuntu"
        echo "  2. 리소스 확인"
        echo "     kubectl describe pod $POD_NAME -n default"
    else
        echo "🔴 상태: 비정상 ($POD_STATUS)"
        echo ""
        echo "권장 조치:"
        echo "  1. Pod 재시작"
        echo "     kubectl delete pod $POD_NAME -n default"
        echo "  2. 로그 확인"
        echo "     kubectl logs -n default $POD_NAME"
    fi
fi

echo ""
EOF

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ PostgreSQL 진단 완료"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "상세 문서: docs/troubleshooting/POSTGRESQL_SCHEDULING_ERROR.md"
echo ""

