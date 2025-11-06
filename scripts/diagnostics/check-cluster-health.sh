#!/bin/bash
# Kubernetes 클러스터 상태 점검 스크립트 (원격)
# Master 노드에 SSH로 접속하여 클러스터 상태 확인
# 로컬 환경을 깨끗하게 유지하기 위해 원격 점검

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 Kubernetes 클러스터 상태 점검 (원격)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Terraform에서 Master IP 가져오기
cd "$TERRAFORM_DIR"
MASTER_IP=$(terraform output -raw master_public_ip 2>/dev/null || echo "")

if [ -z "$MASTER_IP" ]; then
    echo "❌ Master IP를 가져올 수 없습니다."
    echo "   Terraform output을 확인하세요: terraform output master_public_ip"
    exit 1
fi

# SSH 키 경로 확인
SSH_KEY="${HOME}/.ssh/sesacthon"
if [ ! -f "$SSH_KEY" ]; then
    SSH_KEY="${HOME}/.ssh/id_rsa"
    if [ ! -f "$SSH_KEY" ]; then
        echo "❌ SSH 키를 찾을 수 없습니다."
        echo "   $HOME/.ssh/sesacthon 또는 $HOME/.ssh/id_rsa 필요"
        exit 1
    fi
fi

echo "📋 Master 노드: $MASTER_IP"
echo "🔑 SSH 키: $SSH_KEY"
echo ""
echo "🔌 Master 노드에 연결 중..."
echo ""

# Master 노드에서 전체 점검 실행
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no ubuntu@$MASTER_IP 'bash -s' << 'REMOTE_CHECK'
set -e

ERRORS=0
WARNINGS=0

# kubectl 연결 확인
if ! kubectl cluster-info &>/dev/null; then
    echo "❌ Kubernetes 클러스터에 연결할 수 없습니다."
    exit 1
fi

# 1. 노드 상태 확인
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣ 노드 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

NODES=$(kubectl get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')
READY_NODES=$(kubectl get nodes --no-headers 2>/dev/null | grep -c " Ready " || echo "0")
EXPECTED_NODES=4  # Master, Worker-1, Worker-2, Storage

echo "📊 노드 상태: $READY_NODES / $NODES Ready (예상: $EXPECTED_NODES)"
kubectl get nodes -o wide
echo ""

if [ "$NODES" -ne "$EXPECTED_NODES" ]; then
    echo "❌ 노드 개수 불일치 (예상: $EXPECTED_NODES, 실제: $NODES)"
    ((ERRORS++))
elif [ "$READY_NODES" -ne "$EXPECTED_NODES" ]; then
    echo "⚠️  일부 노드가 Ready 상태가 아닙니다"
    ((WARNINGS++))
else
    echo "✅ 모든 노드 Ready"
fi

# 노드 레이블 확인
echo ""
echo "📋 노드 레이블 확인:"
STORAGE_LABEL=$(kubectl get nodes k8s-storage --show-labels --no-headers 2>/dev/null | grep -o "workload=storage" || echo "")
if [ -n "$STORAGE_LABEL" ]; then
    echo "  ✅ k8s-storage: workload=storage"
else
    echo "  ❌ k8s-storage: workload=storage 레이블 없음"
    ((ERRORS++))
fi
echo ""

# 2. 시스템 Pod 상태
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣ 시스템 Pod 상태 (kube-system)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

NOT_READY_PODS=$(kubectl get pods -n kube-system --field-selector=status.phase!=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')

if [ "$NOT_READY_PODS" -gt 0 ]; then
    echo "⚠️  비정상 Pod: $NOT_READY_PODS개"
    kubectl get pods -n kube-system --field-selector=status.phase!=Running
    ((WARNINGS++))
else
    echo "✅ 모든 시스템 Pod 실행 중"
fi

# EBS CSI Driver 확인
EBS_CSI=$(kubectl get pods -n kube-system | grep ebs-csi | grep -c "Running" || echo "0")
if [ "$EBS_CSI" -ge 2 ]; then
    echo "✅ EBS CSI Driver: $EBS_CSI개 Pod 실행 중"
else
    echo "❌ EBS CSI Driver: Pod 부족 또는 미실행"
    ((ERRORS++))
fi
echo ""

# 3. StorageClass 확인
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣ StorageClass 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

GP3_SC=$(kubectl get storageclass gp3 2>/dev/null || echo "")
if [ -n "$GP3_SC" ]; then
    echo "✅ gp3 StorageClass 존재"
    kubectl get storageclass gp3
else
    echo "❌ gp3 StorageClass 없음"
    ((ERRORS++))
fi
echo ""

# 4. Helm Release 확인
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣ Helm Release 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

EXPECTED_RELEASES=(
    "kube-prometheus-stack:monitoring"
    "aws-load-balancer-controller:kube-system"
)

# RabbitMQ는 Operator로 관리 (Helm Release 없음)
RABBITMQ_CR=$(kubectl get rabbitmqcluster rabbitmq -n messaging 2>/dev/null || echo "")
if [ -n "$RABBITMQ_CR" ]; then
    echo "  ✅ RabbitMQ: Operator 관리 (RabbitmqCluster CR)"
else
    echo "  ⚠️  RabbitMQ: RabbitmqCluster CR 없음"
    ((WARNINGS++))
fi

# ArgoCD는 kubectl apply로 설치 (Helm Release 없음)
ARGOCD_PODS=$(kubectl get pods -n argocd --no-headers 2>/dev/null | awk '$3 == "Running" {count++} END {print count+0}' || echo "0")
ARGOCD_PODS=$(echo "$ARGOCD_PODS" | tr -d '\n\r\t ' | sed 's/[^0-9]//g')
[ -z "$ARGOCD_PODS" ] && ARGOCD_PODS="0"
if [ "$ARGOCD_PODS" -gt 0 ]; then
    echo "  ✅ ArgoCD: $ARGOCD_PODS Pod 실행 중 (kubectl apply로 설치)"
else
    echo "  ⚠️  ArgoCD: Pod 실행 중 아님"
    ((WARNINGS++))
fi

# set -e를 일시적으로 해제하여 helm status 실패 시에도 계속 진행
set +e
# Helm 설치 여부 확인
HELM_CHECK=$(which helm 2>/dev/null || echo "")
if [ -z "$HELM_CHECK" ]; then
    echo "  ⚠️  Helm이 설치되지 않았습니다 (Helm Release 확인 불가)"
    echo ""
    echo "  📋 Monitoring 상태 (Helm 없이 확인):"
    PROM_PODS=$(kubectl get pods -n monitoring --no-headers 2>/dev/null | grep -c "Running" || echo "0")
    GRAFANA_PODS=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=grafana --no-headers 2>/dev/null | grep -c "Running" || echo "0")
    if [ "$PROM_PODS" -gt 0 ] || [ "$GRAFANA_PODS" -gt 0 ]; then
        echo "    ✅ Monitoring Pod 실행 중 (Prometheus: $PROM_PODS, Grafana: $GRAFANA_PODS)"
    else
        echo "    ⚠️  Monitoring Pod 실행 중 아님"
        ((WARNINGS++))
    fi
    
    ARGOCD_PODS=$(kubectl get pods -n argocd --no-headers 2>/dev/null | grep -c "Running" || echo "0")
    if [ "$ARGOCD_PODS" -gt 0 ]; then
        echo "    ✅ ArgoCD Pod 실행 중 ($ARGOCD_PODS개)"
    else
        echo "    ⚠️  ArgoCD Pod 실행 중 아님"
        ((WARNINGS++))
    fi
    ((WARNINGS++))
else
    for release_info in "${EXPECTED_RELEASES[@]}"; do
        IFS=':' read -r release_name namespace <<< "$release_info"
        RELEASE_STATUS=$(helm status "$release_name" -n "$namespace" 2>/dev/null | grep "STATUS:" | awk '{print $2}' | tr -d '\n\r ' || echo "not_found")
        
        if [ "$RELEASE_STATUS" == "deployed" ]; then
            echo "  ✅ $release_name ($namespace): deployed"
        elif [ "$RELEASE_STATUS" == "not_found" ]; then
            # helm list로 재확인
            HELM_LIST=$(helm list -n "$namespace" 2>/dev/null | grep "$release_name" || echo "")
            if [ -n "$HELM_LIST" ]; then
                HELM_STATUS=$(echo "$HELM_LIST" | awk '{print $9}' | tr -d '\n\r ')
                if [ -n "$HELM_STATUS" ]; then
                    echo "  ⚠️  $release_name ($namespace): $HELM_STATUS"
                    ((WARNINGS++))
                else
                    echo "  ✅ $release_name ($namespace): 설치됨 (상태: 확인됨)"
                fi
            else
                echo "  ❌ $release_name ($namespace): 설치되지 않음"
                ((ERRORS++))
            fi
        elif [ -z "$RELEASE_STATUS" ] || [ "$RELEASE_STATUS" = "" ]; then
            # helm list로 재확인 (helm status가 실패했지만 설치되어 있을 수 있음)
            HELM_LIST_CHECK=$(helm list -n "$namespace" 2>/dev/null | grep "$release_name" | awk 'END {print NR}' || echo "0")
            HELM_LIST_CHECK=$(echo "$HELM_LIST_CHECK" | tr -d '\n\r\t ' | sed 's/[^0-9]//g')
            if [ -z "$HELM_LIST_CHECK" ]; then
                HELM_LIST_CHECK="0"
            fi
            if [ "$HELM_LIST_CHECK" -gt 0 ]; then
                echo "  ✅ $release_name ($namespace): 설치됨 (helm status 확인 불가)"
            else
                echo "  ⚠️  $release_name ($namespace): 상태 확인 불가"
                echo "      Pod 상태로 확인: kubectl get pods -n $namespace"
                ((WARNINGS++))
            fi
        else
            echo "  ⚠️  $release_name ($namespace): $RELEASE_STATUS"
            ((WARNINGS++))
        fi
    done
fi
set -e
echo ""

# 5. 애플리케이션 Pod 상태
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣ 애플리케이션 Pod 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# RabbitMQ (Operator 관리 - 단일 Pod)
# 이름 패턴으로 직접 찾기 (라벨이 다를 수 있음)
set +e
RABBITMQ_PODS=$(kubectl get pods -n messaging --no-headers 2>/dev/null | awk '$1 ~ /^rabbitmq.*server.*/ && $3 == "Running" {count++} END {print count+0}' || echo "0")
set -e

# 숫자 정규화 (모든 공백/줄바꿈 제거 후 숫자만 추출)
RABBITMQ_PODS=$(echo "$RABBITMQ_PODS" | tr -d '\n\r\t ' | sed 's/[^0-9]//g')
if [ -z "$RABBITMQ_PODS" ] || ! [[ "$RABBITMQ_PODS" =~ ^[0-9]+$ ]]; then
    RABBITMQ_PODS="0"
fi

RABBITMQ_EXPECTED=1
if [ "$RABBITMQ_PODS" -eq "$RABBITMQ_EXPECTED" ] 2>/dev/null; then
    echo "✅ RabbitMQ: $RABBITMQ_PODS/$RABBITMQ_EXPECTED Pod 실행 중 (Operator 관리)"
else
    echo "⚠️  RabbitMQ: $RABBITMQ_PODS/$RABBITMQ_EXPECTED Pod (예상: $RABBITMQ_EXPECTED, Operator 관리)"
    echo "  Pod 목록:"
    kubectl get pods -n messaging 2>/dev/null | grep rabbitmq || kubectl get pods -n messaging
    ((WARNINGS++))
fi

# Redis
REDIS_PODS=$(kubectl get pods -n default -l app=redis --no-headers 2>/dev/null | grep -c "Running" || echo "0")
if [ "$REDIS_PODS" -ge 1 ]; then
    echo "✅ Redis: $REDIS_PODS Pod 실행 중"
else
    echo "⚠️  Redis: Pod 실행 중 아님"
    kubectl get pods -n default -l app=redis 2>/dev/null || true
    ((WARNINGS++))
fi

# Prometheus
PROM_PODS=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus --no-headers 2>/dev/null | grep -c "Running" || echo "0")
if [ "$PROM_PODS" -ge 1 ]; then
    echo "✅ Prometheus: $PROM_PODS Pod 실행 중"
else
    echo "⚠️  Prometheus: Pod 실행 중 아님"
    ((WARNINGS++))
fi

# ArgoCD
ARGOCD_PODS=$(kubectl get pods -n argocd --no-headers 2>/dev/null | grep -c "Running" || echo "0")
if [ "$ARGOCD_PODS" -ge 1 ]; then
    echo "✅ ArgoCD: $ARGOCD_PODS Pod 실행 중"
else
    echo "⚠️  ArgoCD: Pod 실행 중 아님"
    ((WARNINGS++))
fi
echo ""

# 6. PVC 상태
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6️⃣ PVC 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

BOUND_PVC=$(kubectl get pvc -A --no-headers 2>/dev/null | grep -c "Bound" || echo "0")
PENDING_PVC=$(kubectl get pvc -A --no-headers 2>/dev/null | grep -c "Pending" || echo "0")

if [ "$PENDING_PVC" -gt 0 ]; then
    echo "⚠️  Pending PVC: $PENDING_PVC개"
    kubectl get pvc -A | grep Pending
    ((WARNINGS++))
fi

if [ "$BOUND_PVC" -gt 0 ]; then
    echo "✅ Bound PVC: $BOUND_PVC개"
fi
echo ""

# 7. Service 및 Ingress
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "7️⃣ Service 및 Ingress"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# LoadBalancer Service
set +e
LB_SVCS=$(kubectl get svc -A -o json 2>/dev/null | jq -r '.items[] | select(.spec.type=="LoadBalancer") | "\(.metadata.namespace)/\(.metadata.name)"' 2>/dev/null || echo "")
set -e
# 줄바꿈 기준으로 라인 수 계산 (빈 줄 제외)
LB_COUNT=$(echo "$LB_SVCS" | grep -v '^$' | awk 'NF > 0 {count++} END {print count+0}')
# 숫자만 추출
LB_COUNT=$(echo "$LB_COUNT" | tr -d '\n\r\t ' | sed 's/[^0-9]//g')
if [ -z "$LB_COUNT" ] || ! [[ "$LB_COUNT" =~ ^[0-9]+$ ]]; then
    LB_COUNT="0"
fi
if [ "$LB_COUNT" -gt 0 ] 2>/dev/null; then
    echo "📋 LoadBalancer Service: $LB_COUNT개"
    echo "$LB_SVCS" | grep -v '^$' | while read svc; do
        [ -n "$svc" ] && echo "  - $svc"
    done
else
    echo "ℹ️  LoadBalancer Service 없음 (정상 - Ingress 사용)"
fi

# Ingress 검증 (Path-based routing 확인)
INGRESS_COUNT=$(kubectl get ingress -A --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$INGRESS_COUNT" -gt 0 ] 2>/dev/null; then
    echo "✅ Ingress: $INGRESS_COUNT개"
    kubectl get ingress -A
    echo ""
    
    # Path-based routing 검증
    echo "📋 Ingress 라우팅 검증 (Path-based routing):"
    
    # 1. ALB 그룹 확인
    ALB_GROUP_COUNT=0
    PATH_BASED_COUNT=0
    HOST_BASED_COUNT=0
    
    set +e  # jsonpath 실패해도 계속 진행
    for ns in argocd monitoring default; do
        INGRESS_NAMES=$(kubectl get ingress -n "$ns" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")
        if [ -z "$INGRESS_NAMES" ]; then
            continue
        fi
        
        for ing_name in $INGRESS_NAMES; do
            if [ -n "$ing_name" ]; then
                # ALB 그룹 annotation 확인
                ALB_GROUP=$(kubectl get ingress "$ing_name" -n "$ns" -o jsonpath='{.metadata.annotations.alb\.ingress\.kubernetes\.io/group\.name}' 2>/dev/null || echo "")
                if [ -n "$ALB_GROUP" ] && [ "$ALB_GROUP" != "<no value>" ]; then
                    ALB_GROUP_COUNT=$((ALB_GROUP_COUNT + 1))
                fi
                
                # Host 확인 (단일 도메인이면 path-based)
                HOST=$(kubectl get ingress "$ing_name" -n "$ns" -o jsonpath='{.spec.rules[0].host}' 2>/dev/null || echo "")
                PATHS=$(kubectl get ingress "$ing_name" -n "$ns" -o jsonpath='{.spec.rules[0].http.paths[*].path}' 2>/dev/null || echo "")
                
                if [ -n "$PATHS" ] && [ "$PATHS" != "<no value>" ]; then
                    FIRST_PATH=$(echo "$PATHS" | awk '{print $1}' | tr -d ' ')
                    # Path가 있고, host가 동일 도메인이면 path-based
                    if [ -n "$FIRST_PATH" ] && [ "$FIRST_PATH" != "" ] && echo "$FIRST_PATH" | grep -q "^/" && [ "$HOST" = "growbin.app" ]; then
                        PATH_BASED_COUNT=$((PATH_BASED_COUNT + 1))
                        echo "  ✅ $ing_name ($ns): Path-based ($FIRST_PATH)"
                    elif [ -n "$HOST" ] && [ "$HOST" != "growbin.app" ]; then
                        HOST_BASED_COUNT=$((HOST_BASED_COUNT + 1))
                        echo "  ⚠️  $ing_name ($ns): Host-based ($HOST)"
                    fi
                fi
            fi
        done
    done
    set -e
    
    if [ "$ALB_GROUP_COUNT" -gt 0 ]; then
        echo "  ✅ ALB 그룹 설정: $ALB_GROUP_COUNT개 Ingress가 동일 ALB 그룹 사용 (growbin-alb)"
    fi
    
    if [ "$PATH_BASED_COUNT" -gt 0 ]; then
        echo "  ✅ Path-based routing: $PATH_BASED_COUNT개 Ingress 확인됨"
    else
        echo "  ⚠️  Path-based routing Ingress 없음 (확인 필요)"
        ((WARNINGS++))
    fi
    
    if [ "$HOST_BASED_COUNT" -gt 0 ]; then
        echo "  ⚠️  Host-based routing: $HOST_BASED_COUNT개 Ingress (path-based 권장)"
        ((WARNINGS++))
    fi
else
    echo "ℹ️  Ingress 없음 (아직 생성되지 않음)"
fi
echo ""

# 8. etcd 상태
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "8️⃣ etcd 상태"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

set +e
# etcd 인증서 경로 자동 감지 (kubeadm 기본 경로)
ETCD_CA="/etc/kubernetes/pki/etcd/ca.crt"
ETCD_CERT="/etc/kubernetes/pki/etcd/server.crt"
ETCD_KEY="/etc/kubernetes/pki/etcd/server.key"

# 인증서 파일 존재 확인
if [ ! -f "$ETCD_CA" ] || [ ! -f "$ETCD_CERT" ] || [ ! -f "$ETCD_KEY" ]; then
    # 대체 경로 시도
    ETCD_CA="/etc/etcd/pki/ca.crt"
    ETCD_CERT="/etc/etcd/pki/apiserver-etcd-client.crt"
    ETCD_KEY="/etc/etcd/pki/apiserver-etcd-client.key"
fi

# etcdctl 설치 확인
if ! which etcdctl &>/dev/null; then
    echo "⚠️  etcdctl이 설치되지 않았습니다"
    echo "   상세 확인: ./scripts/check-etcd-health.sh"
    ((WARNINGS++))
elif [ -f "$ETCD_CA" ] && [ -f "$ETCD_CERT" ] && [ -f "$ETCD_KEY" ]; then
    # etcd health check
    ETCD_HEALTH=$(sudo ETCDCTL_API=3 etcdctl endpoint health \
        --endpoints=https://127.0.0.1:2379 \
        --cacert="$ETCD_CA" \
        --cert="$ETCD_CERT" \
        --key="$ETCD_KEY" \
        2>&1)
    
    ETCD_EXIT_CODE=$?
    
    if [ $ETCD_EXIT_CODE -eq 0 ] && echo "$ETCD_HEALTH" | grep -q "is healthy"; then
        echo "✅ etcd: healthy"
    else
        echo "⚠️  etcd: 상태 확인 불가 또는 비정상"
        echo "   오류: $(echo "$ETCD_HEALTH" | head -1)"
        echo "   상세 확인: ./scripts/check-etcd-health.sh"
        ((WARNINGS++))
    fi
else
    echo "⚠️  etcd 인증서를 찾을 수 없습니다"
    echo "   예상 경로: /etc/kubernetes/pki/etcd/"
    echo "   상세 확인: ./scripts/check-etcd-health.sh"
    ((WARNINGS++))
fi
set -e
echo ""

# 9. 요약
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 점검 요약"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ARGOCD_PASSWORD=$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" 2>/dev/null | base64 -d || echo "N/A")
ARGOCD_HOSTNAME=$(kubectl get svc argocd-server -n argocd -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "N/A")

if [ "$ERRORS" -eq 0 ] && [ "$WARNINGS" -eq 0 ]; then
    echo "✅ 클러스터 상태 양호!"
    echo ""
    echo "📋 주요 정보:"
    echo "  - 노드: $READY_NODES/$NODES Ready"
    echo "  - Helm Release: 모두 deployed"
    echo "  - 시스템 Pod: 정상"
    echo ""
    echo "🔗 접속 정보:"
    echo "  - ArgoCD: https://${ARGOCD_HOSTNAME}:8080"
    echo "    Username: admin"
    echo "    Password: $ARGOCD_PASSWORD"
    echo ""
    exit 0
elif [ "$ERRORS" -eq 0 ]; then
    echo "⚠️  경고 $WARNINGS개 (치명적 오류 없음)"
    echo ""
    echo "💡 권장 사항:"
    echo "   - 위의 경고 항목 확인"
    echo "   - Pod 로그 확인: kubectl logs <pod-name> -n <namespace>"
    exit 0
else
    echo "❌ 오류 $ERRORS개, 경고 $WARNINGS개"
    echo ""
    echo "💡 다음 단계:"
    echo "   1. 오류 항목 확인"
    echo "   2. Pod 이벤트 확인: kubectl describe pod <pod-name> -n <namespace>"
    echo "   3. 로그 확인: kubectl logs <pod-name> -n <namespace>"
    exit 1
fi

REMOTE_CHECK

# SSH 실행 결과 확인
EXIT_CODE=$?

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 원격 점검 완료"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ 클러스터 점검이 성공적으로 완료되었습니다."
else
    echo "⚠️  일부 문제가 발견되었습니다. 위의 결과를 확인하세요."
fi

exit $EXIT_CODE
