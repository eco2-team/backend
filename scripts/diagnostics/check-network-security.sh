#!/bin/bash
# 네트워크 보안 점검 스크립트
# MQ, Redis, PostgreSQL 외부 접근 차단 확인

set -e

MASTER_IP=${1:-""}
SSH_USER=${2:-"ubuntu"}

if [ -z "$MASTER_IP" ]; then
    echo "사용법: $0 <MASTER_IP> [SSH_USER]"
    echo "예시: $0 52.79.238.50 ubuntu"
    exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔒 네트워크 보안 점검"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Master 노드: $MASTER_IP"
echo "SSH 사용자: $SSH_USER"
echo ""

# 1. Service 타입 확인
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣ Service 타입 확인 (외부 포트 노출 여부)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh $SSH_USER@$MASTER_IP << 'EOF'
echo "🔍 RabbitMQ Service:"
RABBITMQ_TYPE=$(kubectl get svc -n messaging rabbitmq -o jsonpath='{.spec.type}' 2>/dev/null)
if [ -z "$RABBITMQ_TYPE" ]; then
    echo "  ⚠️  Service 없음"
elif [ "$RABBITMQ_TYPE" = "ClusterIP" ]; then
    echo "  ✅ ClusterIP (외부 접근 차단)"
else
    echo "  ❌ $RABBITMQ_TYPE (외부 접근 가능!)"
fi

RABBITMQ_CLUSTER_IP=$(kubectl get svc -n messaging rabbitmq -o jsonpath='{.spec.clusterIP}' 2>/dev/null)
if [ -n "$RABBITMQ_CLUSTER_IP" ]; then
    echo "  ClusterIP: $RABBITMQ_CLUSTER_IP"
    echo "  DNS: rabbitmq.messaging.svc.cluster.local:5672"
fi
echo ""

echo "🔍 Redis Service:"
REDIS_TYPE=$(kubectl get svc -n default redis -o jsonpath='{.spec.type}' 2>/dev/null)
if [ -z "$REDIS_TYPE" ]; then
    echo "  ⚠️  Service 없음"
elif [ "$REDIS_TYPE" = "ClusterIP" ]; then
    echo "  ✅ ClusterIP (외부 접근 차단)"
else
    echo "  ❌ $REDIS_TYPE (외부 접근 가능!)"
fi

REDIS_CLUSTER_IP=$(kubectl get svc -n default redis -o jsonpath='{.spec.clusterIP}' 2>/dev/null)
if [ -n "$REDIS_CLUSTER_IP" ]; then
    echo "  ClusterIP: $REDIS_CLUSTER_IP"
    echo "  DNS: redis.default.svc.cluster.local:6379"
fi
echo ""

echo "🔍 PostgreSQL Service:"
POSTGRES_TYPE=$(kubectl get svc -n default postgres -o jsonpath='{.spec.type}' 2>/dev/null)
if [ -z "$POSTGRES_TYPE" ]; then
    echo "  ⚠️  Service 없음"
elif [ "$POSTGRES_TYPE" = "ClusterIP" ]; then
    echo "  ✅ ClusterIP (외부 접근 차단)"
else
    echo "  ❌ $POSTGRES_TYPE (외부 접근 가능!)"
fi

POSTGRES_CLUSTER_IP=$(kubectl get svc -n default postgres -o jsonpath='{.spec.clusterIP}' 2>/dev/null)
if [ -n "$POSTGRES_CLUSTER_IP" ]; then
    echo "  ClusterIP: $POSTGRES_CLUSTER_IP"
    echo "  DNS: postgres.default.svc.cluster.local:5432"
fi
echo ""
EOF

# 2. NetworkPolicy 확인
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣ NetworkPolicy 확인 (내부 접근 제어)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh $SSH_USER@$MASTER_IP << 'EOF'
echo "🛡️ RabbitMQ NetworkPolicy:"
if kubectl get networkpolicy -n messaging rabbitmq-ingress &>/dev/null; then
    echo "  ✅ NetworkPolicy 있음"
    kubectl get networkpolicy -n messaging rabbitmq-ingress -o jsonpath='{.spec.ingress[*].from[*].podSelector.matchLabels}' 2>/dev/null && echo ""
else
    echo "  ⚠️  NetworkPolicy 없음 (모든 Pod 접근 가능)"
fi
echo ""

echo "🛡️ Redis NetworkPolicy:"
if kubectl get networkpolicy -n default redis-ingress &>/dev/null; then
    echo "  ✅ NetworkPolicy 있음"
    kubectl get networkpolicy -n default redis-ingress -o jsonpath='{.spec.ingress[*].from[*].podSelector.matchLabels}' 2>/dev/null && echo ""
else
    echo "  ⚠️  NetworkPolicy 없음 (모든 Pod 접근 가능)"
fi
echo ""

echo "🛡️ PostgreSQL NetworkPolicy:"
if kubectl get networkpolicy -n default postgres-ingress &>/dev/null; then
    echo "  ✅ NetworkPolicy 있음"
    kubectl get networkpolicy -n default postgres-ingress -o jsonpath='{.spec.ingress[*].from[*].podSelector.matchLabels}' 2>/dev/null && echo ""
else
    echo "  ⚠️  NetworkPolicy 없음 (모든 Pod 접근 가능)"
fi
echo ""
EOF

# 3. 외부 포트 노출 확인 (전체 클러스터)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣ 외부 포트 노출 확인 (클러스터 전체)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh $SSH_USER@$MASTER_IP << 'EOF'
echo "🔍 NodePort Service:"
NODEPORTS=$(kubectl get svc -A --no-headers 2>/dev/null | grep NodePort || echo "")
if [ -z "$NODEPORTS" ]; then
    echo "  ✅ NodePort Service 없음 (안전)"
else
    echo "  ⚠️  NodePort Service 발견:"
    echo "$NODEPORTS" | awk '{printf "    %s (%s) - Port: %s\n", $2, $1, $6}'
fi
echo ""

echo "🔍 LoadBalancer Service:"
LOADBALANCERS=$(kubectl get svc -A --no-headers 2>/dev/null | grep LoadBalancer || echo "")
if [ -z "$LOADBALANCERS" ]; then
    echo "  ✅ LoadBalancer Service 없음"
else
    echo "  ℹ️  LoadBalancer Service 발견 (ALB Ingress용):"
    echo "$LOADBALANCERS" | awk '{printf "    %s (%s)\n", $2, $1}'
fi
echo ""
EOF

# 4. Security Group 확인 (AWS)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣ Security Group 확인 (AWS 레벨)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Worker SG 확인 (로컬에서 실행)
if command -v aws &>/dev/null; then
    echo "🔍 Worker Node Security Group 인바운드 규칙:"
    
    # Terraform outputs에서 Worker SG ID 가져오기
    WORKER_SG_ID=$(cd terraform 2>/dev/null && terraform output -raw worker_security_group_id 2>/dev/null || echo "")
    
    if [ -n "$WORKER_SG_ID" ]; then
        echo "  Security Group ID: $WORKER_SG_ID"
        echo ""
        
        # 인바운드 규칙 확인
        aws ec2 describe-security-groups --group-ids $WORKER_SG_ID --query 'SecurityGroups[0].IpPermissions[].[FromPort,ToPort,IpProtocol,IpRanges[0].CidrIp]' --output table 2>/dev/null || echo "  AWS CLI 오류"
        
        # 5432, 6379, 5672 포트 확인
        echo ""
        echo "🔍 DB/Cache/MQ 포트 노출 확인:"
        
        POSTGRES_EXPOSED=$(aws ec2 describe-security-groups --group-ids $WORKER_SG_ID --query "SecurityGroups[0].IpPermissions[?FromPort==\`5432\`].IpRanges[0].CidrIp" --output text 2>/dev/null)
        if [ -n "$POSTGRES_EXPOSED" ] && [ "$POSTGRES_EXPOSED" != "None" ]; then
            echo "  ⚠️  PostgreSQL Port (5432) 노출: $POSTGRES_EXPOSED"
        else
            echo "  ✅ PostgreSQL Port (5432) 차단"
        fi
        
        REDIS_EXPOSED=$(aws ec2 describe-security-groups --group-ids $WORKER_SG_ID --query "SecurityGroups[0].IpPermissions[?FromPort==\`6379\`].IpRanges[0].CidrIp" --output text 2>/dev/null)
        if [ -n "$REDIS_EXPOSED" ] && [ "$REDIS_EXPOSED" != "None" ]; then
            echo "  ⚠️  Redis Port (6379) 노출: $REDIS_EXPOSED"
        else
            echo "  ✅ Redis Port (6379) 차단"
        fi
        
        RABBITMQ_EXPOSED=$(aws ec2 describe-security-groups --group-ids $WORKER_SG_ID --query "SecurityGroups[0].IpPermissions[?FromPort==\`5672\`].IpRanges[0].CidrIp" --output text 2>/dev/null)
        if [ -n "$RABBITMQ_EXPOSED" ] && [ "$RABBITMQ_EXPOSED" != "None" ]; then
            echo "  ⚠️  RabbitMQ Port (5672) 노출: $RABBITMQ_EXPOSED"
        else
            echo "  ✅ RabbitMQ Port (5672) 차단"
        fi
    else
        echo "  ⚠️  Terraform output을 찾을 수 없습니다"
        echo "  수동 확인: AWS Console → EC2 → Security Groups"
    fi
else
    echo "  ⚠️  AWS CLI가 설치되지 않음"
    echo "  수동 확인: AWS Console → EC2 → Security Groups"
fi
echo ""

# 5. 연결 테스트 (외부에서 접근 시도)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣ 외부 접근 테스트 (로컬에서 시도)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "🔍 PostgreSQL (5432) 접근 시도:"
timeout 2 nc -zv $MASTER_IP 5432 2>&1 | grep -i "succeeded\|refused\|timed out" || echo "  ✅ 접근 차단 (타임아웃)"

echo ""
echo "🔍 Redis (6379) 접근 시도:"
timeout 2 nc -zv $MASTER_IP 6379 2>&1 | grep -i "succeeded\|refused\|timed out" || echo "  ✅ 접근 차단 (타임아웃)"

echo ""
echo "🔍 RabbitMQ (5672) 접근 시도:"
timeout 2 nc -zv $MASTER_IP 5672 2>&1 | grep -i "succeeded\|refused\|timed out" || echo "  ✅ 접근 차단 (타임아웃)"

echo ""

# 6. 최종 요약
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 보안 점검 요약"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh $SSH_USER@$MASTER_IP << 'EOF'
RABBITMQ_TYPE=$(kubectl get svc -n messaging rabbitmq -o jsonpath='{.spec.type}' 2>/dev/null || echo "unknown")
REDIS_TYPE=$(kubectl get svc -n default redis -o jsonpath='{.spec.type}' 2>/dev/null || echo "unknown")
POSTGRES_TYPE=$(kubectl get svc -n default postgres -o jsonpath='{.spec.type}' 2>/dev/null || echo "unknown")

RABBITMQ_NP=$(kubectl get networkpolicy -n messaging rabbitmq-ingress 2>/dev/null && echo "yes" || echo "no")
REDIS_NP=$(kubectl get networkpolicy -n default redis-ingress 2>/dev/null && echo "yes" || echo "no")
POSTGRES_NP=$(kubectl get networkpolicy -n default postgres-ingress 2>/dev/null && echo "yes" || echo "no")

echo "┌─────────────┬──────────────┬─────────────────┬────────────────┐"
echo "│ Service     │ Service Type │ 외부 접근       │ NetworkPolicy  │"
echo "├─────────────┼──────────────┼─────────────────┼────────────────┤"

# RabbitMQ
printf "│ %-11s │ %-12s │ " "RabbitMQ" "$RABBITMQ_TYPE"
if [ "$RABBITMQ_TYPE" = "ClusterIP" ]; then
    printf "%-15s │ " "✅ 차단"
else
    printf "%-15s │ " "❌ 가능"
fi
if [ "$RABBITMQ_NP" = "yes" ]; then
    printf "%-14s │\n" "✅ 있음"
else
    printf "%-14s │\n" "⚠️  없음"
fi

# Redis
printf "│ %-11s │ %-12s │ " "Redis" "$REDIS_TYPE"
if [ "$REDIS_TYPE" = "ClusterIP" ]; then
    printf "%-15s │ " "✅ 차단"
else
    printf "%-15s │ " "❌ 가능"
fi
if [ "$REDIS_NP" = "yes" ]; then
    printf "%-14s │\n" "✅ 있음"
else
    printf "%-14s │\n" "⚠️  없음"
fi

# PostgreSQL
printf "│ %-11s │ %-12s │ " "PostgreSQL" "$POSTGRES_TYPE"
if [ "$POSTGRES_TYPE" = "ClusterIP" ]; then
    printf "%-15s │ " "✅ 차단"
else
    printf "%-15s │ " "❌ 가능"
fi
if [ "$POSTGRES_NP" = "yes" ]; then
    printf "%-14s │\n" "✅ 있음"
else
    printf "%-14s │\n" "⚠️  없음"
fi

echo "└─────────────┴──────────────┴─────────────────┴────────────────┘"
echo ""

# 전체 평가
ALL_CLUSTERIP="no"
if [ "$RABBITMQ_TYPE" = "ClusterIP" ] && [ "$REDIS_TYPE" = "ClusterIP" ] && [ "$POSTGRES_TYPE" = "ClusterIP" ]; then
    ALL_CLUSTERIP="yes"
fi

ALL_NETPOL="no"
if [ "$RABBITMQ_NP" = "yes" ] && [ "$REDIS_NP" = "yes" ] && [ "$POSTGRES_NP" = "yes" ]; then
    ALL_NETPOL="yes"
fi

echo "전체 평가:"
if [ "$ALL_CLUSTERIP" = "yes" ] && [ "$ALL_NETPOL" = "yes" ]; then
    echo "  🟢 최고 보안 (ClusterIP + NetworkPolicy)"
elif [ "$ALL_CLUSTERIP" = "yes" ]; then
    echo "  🟡 기본 보안 (ClusterIP만)"
    echo "  권장: NetworkPolicy 추가로 내부 접근 제어"
else
    echo "  🔴 보안 취약 (외부 접근 가능)"
    echo "  즉시: Service 타입을 ClusterIP로 변경 필요!"
fi
echo ""
EOF

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 보안 점검 완료"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "상세 문서: docs/security/EXTERNAL_ACCESS_AUDIT.md"
echo ""

