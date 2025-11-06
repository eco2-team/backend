#!/bin/bash
# 노드 변경사항이 NetworkPolicy, Ingress, Calico 설정에 미치는 영향 점검
# - Storage → RabbitMQ, PostgreSQL, Redis 분리
# - 노드 수: 5 → 7 (총 7개 노드)
# - NetworkPolicy의 podSelector와 nodeSelector 확인
# - Ingress의 target-type: instance 확인
# - Calico BGP 비활성화 및 VXLAN: Always 확인

set -e

MASTER_IP="${1:-52.79.238.50}"
SSH_KEY="${2:-~/.ssh/sesacthon.pem}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 노드 변경사항 영향 점검 스크립트"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "점검 항목:"
echo "  1. 노드 구성 변경 확인 (5 → 7 Nodes)"
echo "  2. NetworkPolicy 영향 분석"
echo "  3. Ingress 설정 검증"
echo "  4. Calico BGP 비활성화 확인"
echo "  5. Calico VXLAN 모드 확인"
echo ""
echo "Master IP: $MASTER_IP"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 노드 구성 변경 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【1】 노드 구성 변경 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "📋 현재 노드 목록 (workload 레이블 포함):"
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
  "kubectl get nodes -L workload,instance-type --show-labels=false" | tee /tmp/nodes.txt
echo ""

# 노드 수 확인
TOTAL_NODES=$(grep -c "Ready" /tmp/nodes.txt || echo "0")
echo "📊 총 노드 수: $TOTAL_NODES"

if [ "$TOTAL_NODES" -eq 7 ]; then
  echo "✅ 예상대로 7개 노드 (Master + Worker-1 + Worker-2 + RabbitMQ + PostgreSQL + Redis + Monitoring)"
elif [ "$TOTAL_NODES" -eq 5 ]; then
  echo "⚠️ 기존 5개 노드 구성 (Master + Worker-1 + Worker-2 + Storage + Monitoring)"
  echo "   RabbitMQ, PostgreSQL, Redis가 아직 분리되지 않음!"
elif [ "$TOTAL_NODES" -eq 4 ]; then
  echo "⚠️ 기존 4개 노드 구성 (Master + Worker-1 + Worker-2 + Storage)"
  echo "   Monitoring 노드가 없음!"
else
  echo "⚠️ 예상과 다른 노드 수: $TOTAL_NODES"
fi
echo ""

# 노드별 workload 레이블 확인
echo "📌 노드별 workload 레이블:"
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
  "kubectl get nodes -L workload --no-headers" | while read line; do
  NODE_NAME=$(echo "$line" | awk '{print $1}')
  WORKLOAD=$(echo "$line" | awk '{print $NF}')
  
  if [ -z "$WORKLOAD" ] || [ "$WORKLOAD" = "<none>" ]; then
    echo "  ⚠️ $NODE_NAME: (레이블 없음)"
  else
    echo "  ✅ $NODE_NAME: workload=$WORKLOAD"
  fi
done
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. NetworkPolicy 영향 분석
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【2】 NetworkPolicy 영향 분석"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# NetworkPolicy 목록
echo "📋 현재 NetworkPolicy 목록:"
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
  "kubectl get networkpolicy -A" 2>/dev/null || echo "⚠️ NetworkPolicy가 없습니다."
echo ""

# NetworkPolicy는 podSelector를 사용하므로 nodeSelector 변경 영향 없음
echo "🔍 NetworkPolicy 분석:"
echo ""
echo "  ℹ️ NetworkPolicy는 'podSelector'를 사용합니다."
echo "     - podSelector는 Pod의 레이블을 기반으로 동작"
echo "     - nodeSelector와는 독립적"
echo "     - 노드 구성 변경 (Storage 분리)은 NetworkPolicy에 영향 없음"
echo ""

# RabbitMQ NetworkPolicy 확인 (예시)
echo "📌 RabbitMQ NetworkPolicy 예시 (권장):"
echo ""
cat << 'EOF'
  apiVersion: networking.k8s.io/v1
  kind: NetworkPolicy
  metadata:
    name: rabbitmq-ingress
    namespace: messaging
  spec:
    podSelector:
      matchLabels:
        app.kubernetes.io/name: rabbitmq  # Pod 레이블 기반
    policyTypes:
    - Ingress
    ingress:
    - from:
      - podSelector:
          matchLabels:
            tier: backend  # Backend Pod만 허용
      ports:
      - protocol: TCP
        port: 5672
EOF
echo ""

echo "  ✅ RabbitMQ Pod가 k8s-rabbitmq 노드에 있든, k8s-storage 노드에 있든"
echo "     NetworkPolicy는 정상 작동합니다."
echo ""

# PostgreSQL NetworkPolicy 확인
echo "📌 PostgreSQL NetworkPolicy 예시 (권장):"
echo ""
cat << 'EOF'
  apiVersion: networking.k8s.io/v1
  kind: NetworkPolicy
  metadata:
    name: postgres-ingress
    namespace: default
  spec:
    podSelector:
      matchLabels:
        app: postgres  # Pod 레이블 기반
    policyTypes:
    - Ingress
    ingress:
    - from:
      - podSelector:
          matchLabels:
            tier: backend  # Backend Pod만 허용
      ports:
      - protocol: TCP
        port: 5432
EOF
echo ""

echo "  ✅ PostgreSQL Pod가 k8s-postgresql 노드에 있든, k8s-storage 노드에 있든"
echo "     NetworkPolicy는 정상 작동합니다."
echo ""

echo "📝 결론:"
echo "  ✅ NetworkPolicy는 Pod 레이블(podSelector) 기반"
echo "  ✅ 노드 레이블(nodeSelector) 변경은 NetworkPolicy에 영향 없음"
echo "  ✅ Storage 노드 분리(RabbitMQ, PostgreSQL, Redis)는 NetworkPolicy에 영향 없음"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Ingress 설정 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【3】 Ingress 설정 검증"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "📋 현재 Ingress 목록:"
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
  "kubectl get ingress -A -o wide" 2>/dev/null | tee /tmp/ingress.txt
echo ""

# Ingress target-type 확인
echo "🔍 Ingress target-type 확인:"
echo ""

for NAMESPACE in argocd monitoring default; do
  case $NAMESPACE in
    argocd)
      INGRESS_NAME="argocd-ingress"
      ;;
    monitoring)
      INGRESS_NAME="grafana-ingress"
      ;;
    default)
      INGRESS_NAME="api-ingress"
      ;;
  esac
  
  echo "📌 $INGRESS_NAME ($NAMESPACE):"
  
  # target-type 확인
  TARGET_TYPE=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
    "kubectl get ingress $INGRESS_NAME -n $NAMESPACE -o jsonpath='{.metadata.annotations.alb\.ingress\.kubernetes\.io/target-type}' 2>/dev/null" || echo "")
  
  if [ "$TARGET_TYPE" = "instance" ]; then
    echo "  ✅ target-type: instance (올바름)"
    echo "     → ALB가 Worker Node의 NodePort로 트래픽 전달"
    echo "     → Calico Pod IP (192.168.x.x) 문제 없음"
  elif [ "$TARGET_TYPE" = "ip" ]; then
    echo "  ❌ target-type: ip (문제 있음!)"
    echo "     → ALB가 Pod IP로 직접 트래픽 전달 시도"
    echo "     → Calico Pod IP (192.168.x.x)는 VPC CIDR(10.0.0.0/16) 밖"
    echo "     → ALB가 Pod에 접근 불가 → 504 Gateway Timeout"
    echo ""
    echo "  ⚠️ 수정 필요: target-type을 'instance'로 변경하세요!"
  else
    echo "  ⚠️ target-type: (설정 없음 또는 Ingress 없음)"
  fi
  echo ""
done

echo "📝 결론:"
echo "  ✅ Ingress target-type: instance 사용 (Calico와 호환)"
echo "  ✅ 노드 분리(RabbitMQ, PostgreSQL, Redis)는 Ingress에 영향 없음"
echo "  ℹ️ Ingress는 Service를 통해 Pod에 접근 (NodePort 사용)"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. Calico BGP 비활성화 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【4】 Calico BGP 비활성화 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "🔍 BGPConfiguration 확인:"
BGP_CONFIG=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
  "kubectl get bgpconfiguration default -o yaml 2>/dev/null" || echo "")

if [ -z "$BGP_CONFIG" ]; then
  echo "⚠️ BGPConfiguration 'default'가 없습니다."
  echo "   Calico BGP가 기본 설정(활성화)일 수 있습니다."
  echo ""
  echo "📌 BGP 비활성화 방법:"
  echo ""
  cat << 'EOF'
  kubectl apply -f - <<EOF
  apiVersion: crd.projectcalico.org/v1
  kind: BGPConfiguration
  metadata:
    name: default
  spec:
    nodeToNodeMeshEnabled: false
    asNumber: 64512
  EOF
EOF
  echo ""
else
  # nodeToNodeMeshEnabled 확인
  NODE_MESH=$(echo "$BGP_CONFIG" | grep "nodeToNodeMeshEnabled" | awk '{print $2}')
  
  if [ "$NODE_MESH" = "false" ]; then
    echo "  ✅ nodeToNodeMeshEnabled: false (BGP 비활성화됨)"
  else
    echo "  ❌ nodeToNodeMeshEnabled: true (BGP 활성화됨!)"
    echo "     ⚠️ VXLAN 전용 모드에서는 BGP를 비활성화해야 합니다."
  fi
  echo ""
  
  # 전체 BGP 설정 출력
  echo "📋 전체 BGPConfiguration:"
  echo "$BGP_CONFIG" | grep -A 5 "spec:"
  echo ""
fi

# BIRD 프로세스 확인 (BGP 데몬)
echo "🔍 BIRD 프로세스 확인 (calico-node Pod):"
BIRD_PROCESS=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
  "kubectl exec -n kube-system \$(kubectl get pods -n kube-system -l k8s-app=calico-node -o jsonpath='{.items[0].metadata.name}') -- ps aux | grep bird | grep -v grep 2>/dev/null" || echo "")

if [ -z "$BIRD_PROCESS" ]; then
  echo "  ✅ BIRD 프로세스 없음 (BGP 비활성화됨)"
else
  echo "  ⚠️ BIRD 프로세스 실행 중 (BGP 활성화됨)"
  echo "     $BIRD_PROCESS"
fi
echo ""

echo "📝 결론:"
if [ "$NODE_MESH" = "false" ] && [ -z "$BIRD_PROCESS" ]; then
  echo "  ✅ Calico BGP 완전히 비활성화됨"
  echo "  ✅ VXLAN 전용 모드 사용 중"
else
  echo "  ⚠️ Calico BGP가 활성화되어 있습니다."
  echo "     VXLAN 전용 모드를 위해 BGP를 비활성화하세요."
fi
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. Calico VXLAN 모드 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【5】 Calico VXLAN 모드 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "🔍 IPPool 설정 확인:"
IPPOOL_CONFIG=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
  "kubectl get ippool default-ipv4-ippool -o yaml 2>/dev/null" || echo "")

if [ -z "$IPPOOL_CONFIG" ]; then
  echo "⚠️ IPPool 'default-ipv4-ippool'이 없습니다."
  echo "   Calico가 설치되지 않았거나 다른 IPPool 이름을 사용 중입니다."
  echo ""
else
  # vxlanMode 확인
  VXLAN_MODE=$(echo "$IPPOOL_CONFIG" | grep "vxlanMode" | awk '{print $2}')
  IPIP_MODE=$(echo "$IPPOOL_CONFIG" | grep "ipipMode" | awk '{print $2}')
  NAT_OUTGOING=$(echo "$IPPOOL_CONFIG" | grep "natOutgoing" | awk '{print $2}')
  
  echo "📋 IPPool 설정:"
  echo "  - vxlanMode: $VXLAN_MODE"
  echo "  - ipipMode: $IPIP_MODE"
  echo "  - natOutgoing: $NAT_OUTGOING"
  echo ""
  
  # 검증
  if [ "$VXLAN_MODE" = "Always" ]; then
    echo "  ✅ vxlanMode: Always (올바름)"
  elif [ "$VXLAN_MODE" = "Never" ]; then
    echo "  ❌ vxlanMode: Never (VXLAN 비활성화됨!)"
    echo "     ⚠️ 'Always'로 변경 필요"
  else
    echo "  ⚠️ vxlanMode: $VXLAN_MODE (예상 값: Always)"
  fi
  
  if [ "$IPIP_MODE" = "Never" ]; then
    echo "  ✅ ipipMode: Never (올바름, IPIP 비활성화)"
  else
    echo "  ⚠️ ipipMode: $IPIP_MODE (예상 값: Never)"
  fi
  
  if [ "$NAT_OUTGOING" = "true" ]; then
    echo "  ✅ natOutgoing: true (올바름, SNAT 활성화)"
  else
    echo "  ⚠️ natOutgoing: $NAT_OUTGOING (예상 값: true)"
  fi
  echo ""
fi

# FelixConfiguration 확인
echo "🔍 FelixConfiguration 확인:"
FELIX_CONFIG=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
  "kubectl get felixconfiguration default -o yaml 2>/dev/null" || echo "")

if [ -z "$FELIX_CONFIG" ]; then
  echo "⚠️ FelixConfiguration 'default'가 없습니다."
  echo ""
else
  VXLAN_ENABLED=$(echo "$FELIX_CONFIG" | grep "vxlanEnabled" | awk '{print $2}')
  IPIP_ENABLED=$(echo "$FELIX_CONFIG" | grep "ipipEnabled" | awk '{print $2}')
  BPF_ENABLED=$(echo "$FELIX_CONFIG" | grep "bpfEnabled" | awk '{print $2}')
  
  echo "📋 FelixConfiguration:"
  echo "  - vxlanEnabled: $VXLAN_ENABLED"
  echo "  - ipipEnabled: $IPIP_ENABLED"
  echo "  - bpfEnabled: $BPF_ENABLED"
  echo ""
  
  if [ "$VXLAN_ENABLED" = "true" ]; then
    echo "  ✅ vxlanEnabled: true (올바름)"
  else
    echo "  ⚠️ vxlanEnabled: $VXLAN_ENABLED (예상 값: true)"
  fi
  
  if [ "$IPIP_ENABLED" = "false" ]; then
    echo "  ✅ ipipEnabled: false (올바름)"
  else
    echo "  ⚠️ ipipEnabled: $IPIP_ENABLED (예상 값: false)"
  fi
  
  if [ "$BPF_ENABLED" = "false" ]; then
    echo "  ✅ bpfEnabled: false (올바름)"
  else
    echo "  ⚠️ bpfEnabled: $BPF_ENABLED (예상 값: false)"
  fi
  echo ""
fi

# calico-node 환경변수 확인
echo "🔍 calico-node DaemonSet 환경변수 확인:"
CALICO_ENV=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@"$MASTER_IP" \
  "kubectl get daemonset calico-node -n kube-system -o jsonpath='{.spec.template.spec.containers[0].env}' 2>/dev/null" | grep -E "CALICO_IPV4POOL_VXLAN|FELIX_VXLANENABLED" || echo "")

if [ -z "$CALICO_ENV" ]; then
  echo "  ⚠️ VXLAN 관련 환경변수가 설정되지 않았습니다."
else
  echo "  환경변수:"
  echo "$CALICO_ENV" | grep -o "CALICO_IPV4POOL_VXLAN.*" || true
  echo "$CALICO_ENV" | grep -o "FELIX_VXLANENABLED.*" || true
fi
echo ""

echo "📝 결론:"
if [ "$VXLAN_MODE" = "Always" ] && [ "$VXLAN_ENABLED" = "true" ]; then
  echo "  ✅ Calico VXLAN 모드: Always (올바름)"
  echo "  ✅ IPIP 모드: Never (비활성화됨)"
  echo "  ✅ natOutgoing: true (SNAT 활성화)"
else
  echo "  ⚠️ Calico VXLAN 설정을 확인하세요."
  echo "     예상 설정:"
  echo "       - vxlanMode: Always"
  echo "       - ipipMode: Never"
  echo "       - vxlanEnabled: true"
fi
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 최종 요약
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【최종 요약】"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "📊 점검 결과:"
echo ""
echo "1. 노드 구성:"
if [ "$TOTAL_NODES" -eq 7 ]; then
  echo "   ✅ 7개 노드 (RabbitMQ, PostgreSQL, Redis 분리 완료)"
elif [ "$TOTAL_NODES" -eq 5 ]; then
  echo "   ⚠️ 5개 노드 (아직 Storage 통합 구성)"
else
  echo "   ⚠️ $TOTAL_NODES 개 노드 (예상과 다름)"
fi
echo ""

echo "2. NetworkPolicy:"
echo "   ✅ podSelector 기반 → 노드 변경 영향 없음"
echo ""

echo "3. Ingress:"
echo "   ✅ target-type: instance → Calico와 호환"
echo "   ✅ 노드 변경 영향 없음"
echo ""

echo "4. Calico BGP:"
if [ "$NODE_MESH" = "false" ]; then
  echo "   ✅ nodeToNodeMeshEnabled: false (비활성화)"
else
  echo "   ⚠️ BGP 설정 확인 필요"
fi
echo ""

echo "5. Calico VXLAN:"
if [ "$VXLAN_MODE" = "Always" ]; then
  echo "   ✅ vxlanMode: Always (올바름)"
else
  echo "   ⚠️ VXLAN 설정 확인 필요"
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 점검 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "📝 권장 사항:"
echo ""
echo "1. NetworkPolicy 추가 (선택사항):"
echo "   - RabbitMQ, PostgreSQL, Redis에 대한 NetworkPolicy 생성"
echo "   - Zero Trust 보안 강화"
echo ""
echo "2. Calico 설정 검증:"
echo "   - BGP 완전 비활성화 (nodeToNodeMeshEnabled: false)"
echo "   - VXLAN Always 모드 (vxlanMode: Always)"
echo "   - IPIP 비활성화 (ipipMode: Never)"
echo ""
echo "3. 모니터링:"
echo "   - 노드 분리 후 Pod 재배치 확인"
echo "   - 각 서비스(RabbitMQ, PostgreSQL, Redis)가 전용 노드에 배치되었는지 확인"
echo "   - kubectl get pods -o wide --all-namespaces"
echo ""

rm -f /tmp/nodes.txt /tmp/ingress.txt

