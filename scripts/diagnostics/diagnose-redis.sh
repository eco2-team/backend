#!/bin/bash
# Redis 원격 진단 스크립트
# Master 노드에 접속하여 Redis 상태를 종합적으로 진단

set -e

MASTER_IP=${1:-""}
SSH_USER=${2:-"ubuntu"}

if [ -z "$MASTER_IP" ]; then
    echo "사용법: $0 <MASTER_IP> [SSH_USER]"
    echo "예시: $0 52.79.238.50 ubuntu"
    exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 Redis 원격 진단"
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

echo "📦 Deployment 확인:"
kubectl get deployment -n default | grep -E "(NAME|redis)" || echo "  ❌ Redis Deployment 없음"
echo ""

echo "🗂️ Pod 확인:"
kubectl get pods -n default -l app=redis -o wide || echo "  ❌ Redis Pod 없음"
echo ""

echo "🔌 Service 확인:"
kubectl get svc -n default | grep -E "(NAME|redis)" || echo "  ❌ Redis Service 없음"
echo ""

echo "⚙️ ConfigMap 확인:"
kubectl get configmap -n default | grep -E "(NAME|redis)" || echo "  ℹ️  Redis ConfigMap 없음 (선택사항)"
echo ""
EOF

# 2. Pod 상태 상세 분석
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣ Pod 상태 상세 분석"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh $SSH_USER@$MASTER_IP << 'EOF'
POD_COUNT=$(kubectl get pods -n default -l app=redis --no-headers 2>/dev/null | wc -l)

if [ "$POD_COUNT" -eq 0 ]; then
    echo "❌ Redis Pod가 없습니다."
    echo ""
    echo "Deployment 확인:"
    kubectl get deployment -n default redis 2>&1 || echo "  Deployment도 없습니다."
    echo ""
    echo "최근 이벤트:"
    kubectl get events -n default --sort-by='.lastTimestamp' | tail -20
    exit 0
fi

POD_NAME=$(kubectl get pods -n default -l app=redis -o jsonpath='{.items[0].metadata.name}')
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
POD_NAME=$(kubectl get pods -n default -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

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
EOF

# 4. Redis 연결 및 정보
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣ Redis 연결 및 정보"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh $SSH_USER@$MASTER_IP << 'EOF'
POD_NAME=$(kubectl get pods -n default -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

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

echo "🔌 Redis PING 테스트:"
kubectl exec -n default $POD_NAME -- redis-cli ping 2>&1
if [ $? -eq 0 ]; then
    echo "  ✅ 연결 성공"
else
    echo "  ❌ 연결 실패"
fi
echo ""

echo "📊 Redis 서버 정보:"
kubectl exec -n default $POD_NAME -- redis-cli INFO server 2>&1 | grep -E "(redis_version|os|process_id|tcp_port|uptime_in_seconds)"
echo ""

echo "💾 Redis 메모리 정보:"
kubectl exec -n default $POD_NAME -- redis-cli INFO memory 2>&1 | grep -E "(used_memory_human|used_memory_peak_human|maxmemory_human|mem_fragmentation_ratio)"
echo ""

echo "📈 Redis 통계:"
kubectl exec -n default $POD_NAME -- redis-cli INFO stats 2>&1 | grep -E "(total_connections_received|total_commands_processed|instantaneous_ops_per_sec|keyspace_hits|keyspace_misses)"
echo ""

echo "🗂️ 데이터베이스 키 통계:"
kubectl exec -n default $POD_NAME -- redis-cli INFO keyspace 2>&1
echo ""

echo "🔑 샘플 키 조회 (최대 10개):"
kubectl exec -n default $POD_NAME -- redis-cli --scan --count 10 2>&1 | head -10
echo ""
EOF

# 5. 읽기/쓰기 테스트
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣ 읽기/쓰기 테스트"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh $SSH_USER@$MASTER_IP << 'EOF'
POD_NAME=$(kubectl get pods -n default -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -z "$POD_NAME" ]; then
    echo "❌ Pod가 없어 테스트 불가"
    exit 0
fi

POD_STATUS=$(kubectl get pod $POD_NAME -n default -o jsonpath='{.status.phase}')
if [ "$POD_STATUS" != "Running" ]; then
    echo "❌ Pod 상태가 Running이 아님"
    exit 0
fi

TEST_KEY="test_diagnosis_$(date +%s)"
TEST_VALUE="diagnosis_value_$(date +%s)"

echo "📝 쓰기 테스트:"
WRITE_RESULT=$(kubectl exec -n default $POD_NAME -- redis-cli SET "$TEST_KEY" "$TEST_VALUE" EX 60 2>&1)
echo "  SET $TEST_KEY = $TEST_VALUE (TTL 60s)"
echo "  결과: $WRITE_RESULT"
if [ "$WRITE_RESULT" = "OK" ]; then
    echo "  ✅ 쓰기 성공"
else
    echo "  ❌ 쓰기 실패"
fi
echo ""

echo "📖 읽기 테스트:"
READ_RESULT=$(kubectl exec -n default $POD_NAME -- redis-cli GET "$TEST_KEY" 2>&1)
echo "  GET $TEST_KEY"
echo "  결과: $READ_RESULT"
if [ "$READ_RESULT" = "$TEST_VALUE" ]; then
    echo "  ✅ 읽기 성공 (값 일치)"
else
    echo "  ❌ 읽기 실패 (값 불일치)"
fi
echo ""

echo "🗑️ 삭제 테스트:"
DELETE_RESULT=$(kubectl exec -n default $POD_NAME -- redis-cli DEL "$TEST_KEY" 2>&1)
echo "  DEL $TEST_KEY"
echo "  결과: $DELETE_RESULT"
if [ "$DELETE_RESULT" = "1" ]; then
    echo "  ✅ 삭제 성공"
else
    echo "  ⚠️ 삭제 결과 불확실"
fi
echo ""

echo "🔗 Service DNS 테스트:"
kubectl run test-dns --image=busybox --rm -it --restart=Never -- nslookup redis.default.svc.cluster.local 2>&1 | grep -A 5 "Name:"
echo ""
EOF

# 6. 로그 확인
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6️⃣ 로그 확인 (최근 50줄)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh $SSH_USER@$MASTER_IP << 'EOF'
POD_NAME=$(kubectl get pods -n default -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -z "$POD_NAME" ]; then
    echo "❌ Pod가 없어 로그 확인 불가"
    exit 0
fi

echo "📜 Redis 로그:"
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
POD_COUNT=$(kubectl get pods -n default -l app=redis --no-headers 2>/dev/null | wc -l)
if [ "$POD_COUNT" -eq 0 ]; then
    echo "❌ Redis Pod가 없습니다"
    echo "   → Deployment 확인 필요"
    echo "   → kubectl get deployment -n default redis"
    echo ""
fi

POD_NAME=$(kubectl get pods -n default -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$POD_NAME" ]; then
    POD_STATUS=$(kubectl get pod $POD_NAME -n default -o jsonpath='{.status.phase}')
    
    if [ "$POD_STATUS" = "Pending" ]; then
        echo "⚠️ Pod가 Pending 상태입니다"
        echo "   가능한 원인:"
        echo "   1. 이미지 Pull 실패"
        kubectl describe pod $POD_NAME -n default | grep -A 5 "Events:" | grep -i "failed\|error" || echo "      (이벤트 없음)"
        echo ""
        echo "   2. 리소스 부족"
        kubectl describe pod $POD_NAME -n default | grep -A 5 "Events:" | grep -i "insufficient"
        echo ""
    elif [ "$POD_STATUS" = "CrashLoopBackOff" ] || [ "$POD_STATUS" = "Error" ]; then
        echo "❌ Pod가 $POD_STATUS 상태입니다"
        echo "   최근 로그:"
        kubectl logs -n default $POD_NAME --tail=20 2>&1 | tail -10
        echo ""
        echo "   가능한 원인:"
        echo "   1. 설정 오류"
        echo "   2. 포트 충돌"
        echo "   3. 권한 문제"
        echo ""
    elif [ "$POD_STATUS" = "Running" ]; then
        echo "✅ Pod가 Running 상태입니다"
        
        # 재시작 횟수 확인
        RESTART_COUNT=$(kubectl get pod $POD_NAME -n default -o jsonpath='{.status.containerStatuses[0].restartCount}')
        if [ "$RESTART_COUNT" -gt 0 ]; then
            echo "   ⚠️ 재시작 횟수: $RESTART_COUNT"
            echo "   → 이전 로그 확인 필요"
            echo "   → kubectl logs -n default $POD_NAME --previous"
        else
            echo "   재시작: 없음"
        fi
        echo ""
        
        # 연결 테스트
        PING_RESULT=$(kubectl exec -n default $POD_NAME -- redis-cli ping 2>&1)
        if [ "$PING_RESULT" = "PONG" ]; then
            echo "   ✅ Redis 연결 정상"
        else
            echo "   ❌ Redis 연결 실패"
            echo "   → 포트 확인: kubectl describe pod $POD_NAME -n default"
        fi
        echo ""
    fi
fi

# Service 확인
if ! kubectl get svc redis -n default &>/dev/null; then
    echo "❌ Redis Service가 없습니다"
    echo "   → Service 생성 필요"
    echo ""
else
    SERVICE_TYPE=$(kubectl get svc redis -n default -o jsonpath='{.spec.type}')
    echo "ℹ️  Service 타입: $SERVICE_TYPE"
    
    if [ "$SERVICE_TYPE" = "ClusterIP" ]; then
        CLUSTER_IP=$(kubectl get svc redis -n default -o jsonpath='{.spec.clusterIP}')
        echo "   ClusterIP: $CLUSTER_IP"
        echo "   DNS: redis.default.svc.cluster.local"
    fi
    echo ""
fi

# 메모리 경고 확인
if [ -n "$POD_NAME" ] && [ "$POD_STATUS" = "Running" ]; then
    MEMORY_USAGE=$(kubectl exec -n default $POD_NAME -- redis-cli INFO memory 2>&1 | grep "used_memory_human:" | cut -d: -f2)
    MEMORY_PEAK=$(kubectl exec -n default $POD_NAME -- redis-cli INFO memory 2>&1 | grep "used_memory_peak_human:" | cut -d: -f2)
    
    echo "💾 메모리 사용량:"
    echo "   현재: $MEMORY_USAGE"
    echo "   최대: $MEMORY_PEAK"
    echo ""
fi

EOF

# 8. 진단 요약
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "8️⃣ 진단 요약"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh $SSH_USER@$MASTER_IP << 'EOF'
POD_NAME=$(kubectl get pods -n default -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -z "$POD_NAME" ]; then
    echo "🔴 상태: Redis가 배포되지 않음"
    echo ""
    echo "권장 조치:"
    echo "  1. Ansible 플레이북 실행"
    echo "     cd "$PROJECT_ROOT/ansible" && ansible-playbook -i inventory/hosts.ini site.yml --tags redis"
    echo ""
else
    POD_STATUS=$(kubectl get pod $POD_NAME -n default -o jsonpath='{.status.phase}')
    
    if [ "$POD_STATUS" = "Running" ]; then
        # PING 테스트
        kubectl exec -n default $POD_NAME -- redis-cli ping &>/dev/null
        if [ $? -eq 0 ]; then
            echo "🟢 상태: 정상 (Running & PONG)"
            echo ""
            echo "ℹ️  Redis가 정상적으로 작동 중입니다."
            echo ""
            echo "연결 정보:"
            echo "  Host: redis.default.svc.cluster.local"
            echo "  Port: 6379"
            echo "  Protocol: redis://"
            echo ""
            echo "Python 예시:"
            echo '  import redis'
            echo '  r = redis.Redis(host="redis.default.svc.cluster.local", port=6379)'
            echo '  r.ping()'
        else
            echo "🟡 상태: Running이지만 연결 불가"
            echo ""
            echo "권장 조치:"
            echo "  1. 로그 확인"
            echo "     kubectl logs -n default $POD_NAME"
            echo "  2. 포트 확인"
            echo "     kubectl describe pod $POD_NAME -n default | grep Port"
        fi
    elif [ "$POD_STATUS" = "Pending" ]; then
        echo "🟡 상태: Pending (스케줄링 대기)"
        echo ""
        echo "권장 조치:"
        echo "  1. 이벤트 확인"
        echo "     kubectl describe pod $POD_NAME -n default"
        echo "  2. 이미지 Pull 확인"
        echo "     kubectl get events -n default --sort-by='.lastTimestamp'"
    else
        echo "🔴 상태: 비정상 ($POD_STATUS)"
        echo ""
        echo "권장 조치:"
        echo "  1. Pod 재시작"
        echo "     kubectl delete pod $POD_NAME -n default"
        echo "  2. 로그 확인"
        echo "     kubectl logs -n default $POD_NAME"
        echo "  3. 이전 로그 확인"
        echo "     kubectl logs -n default $POD_NAME --previous"
    fi
fi

echo ""
EOF

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Redis 진단 완료"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

