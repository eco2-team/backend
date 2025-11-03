#!/bin/bash
# Master 노드에서 실행할 빠른 수정 스크립트

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔧 RabbitMQ 및 Redis 문제 수정"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. RabbitMQ 재설치 (올바른 이미지 사용)
echo "1️⃣ RabbitMQ 재설치 (이미지 수정)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "기존 RabbitMQ 제거..."
helm uninstall rabbitmq -n messaging 2>/dev/null || true

echo "기존 Pod 삭제 대기..."
sleep 10

echo "⚠️  이제 Ansible을 재실행하세요:"
echo "   cd ansible"
echo "   ansible-playbook -i inventory/hosts.ini continue-install.yml"
echo ""
echo "또는 RabbitMQ만 재설치:"
echo "   helm install rabbitmq bitnami/rabbitmq \\"
echo "     --namespace messaging \\"
echo "     --set auth.username=admin \\"
echo "     --set auth.password=changeme \\"
echo "     --set replicaCount=3 \\"
echo "     --set persistence.enabled=true \\"
echo "     --set persistence.size=20Gi \\"
echo "     --set persistence.storageClass=gp3 \\"
echo "     --set nodeSelector.workload=storage"
echo ""

# 2. Redis 문제 확인
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣ Redis Pod 스케줄링 문제 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kubectl describe pod -l app=redis -n default | grep -A 5 "Events:"
echo ""

echo "Redis Pod 삭제 (재시도):"
kubectl delete pod -l app=redis -n default
echo ""

