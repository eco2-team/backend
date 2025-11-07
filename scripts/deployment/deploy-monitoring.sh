#!/bin/bash

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 Ecoeco 13-Node Monitoring Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 변수 설정
NAMESPACE="default"
MONITORING_DIR="k8s/monitoring"

# Step 1: Node Exporter 배포 (13 Nodes)
echo ""
echo "📊 1. Node Exporter DaemonSet 배포..."
kubectl apply -f ${MONITORING_DIR}/node-exporter.yaml

# Step 2: Prometheus 배포
echo ""
echo "📈 2. Prometheus 배포..."

# Prometheus Rules ConfigMap 생성
echo "  - Creating Prometheus Rules ConfigMap..."
kubectl create configmap prometheus-rules \
  --from-file=${MONITORING_DIR}/prometheus-rules.yaml \
  --namespace=${NAMESPACE} \
  --dry-run=client -o yaml | kubectl apply -f -

# Prometheus Deployment 배포
echo "  - Deploying Prometheus..."
kubectl apply -f ${MONITORING_DIR}/prometheus-deployment.yaml

# Step 3: Grafana 배포
echo ""
echo "📊 3. Grafana 배포..."

# Grafana Dashboards ConfigMap 생성
echo "  - Creating Grafana Dashboards ConfigMap..."
kubectl create configmap grafana-dashboards \
  --from-file=${MONITORING_DIR}/grafana-dashboard-13nodes.json \
  --namespace=${NAMESPACE} \
  --dry-run=client -o yaml | kubectl apply -f -

# Grafana Deployment 배포
echo "  - Deploying Grafana..."
kubectl apply -f ${MONITORING_DIR}/grafana-deployment.yaml

# Step 4: ServiceMonitors 배포 (Optional - Prometheus Operator 사용 시)
echo ""
echo "🎯 4. ServiceMonitors 배포 (Optional)..."
if kubectl get crd servicemonitors.monitoring.coreos.com &> /dev/null; then
  echo "  - Prometheus Operator detected, applying ServiceMonitors..."
  kubectl apply -f ${MONITORING_DIR}/servicemonitors.yaml
else
  echo "  - ⚠️  Prometheus Operator not found, skipping ServiceMonitors"
  echo "  - Prometheus will use pod discovery instead"
fi

# Step 5: 배포 상태 확인
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Monitoring Stack Deployed!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 Deployment Status:"
echo ""

# Node Exporter 상태
echo "Node Exporter:"
kubectl get daemonset node-exporter -n ${NAMESPACE}
echo ""

# Prometheus 상태
echo "Prometheus:"
kubectl get deployment prometheus -n ${NAMESPACE}
kubectl get service prometheus -n ${NAMESPACE}
echo ""

# Grafana 상태
echo "Grafana:"
kubectl get deployment grafana -n ${NAMESPACE}
kubectl get service grafana -n ${NAMESPACE}
echo ""

# Pod 상태 대기
echo "⏳ Waiting for pods to be ready..."
kubectl wait --for=condition=ready pod -l app=prometheus -n ${NAMESPACE} --timeout=300s || true
kubectl wait --for=condition=ready pod -l app=grafana -n ${NAMESPACE} --timeout=300s || true

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎯 Access Information"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Prometheus:"
echo "  kubectl port-forward svc/prometheus 9090:9090 -n ${NAMESPACE}"
echo "  http://localhost:9090"
echo ""
echo "Grafana:"
echo "  kubectl port-forward svc/grafana 3000:3000 -n ${NAMESPACE}"
echo "  http://localhost:3000"
echo "  Username: admin"
echo "  Password: (from secret grafana-admin)"
echo ""
echo "To get Grafana password:"
echo "  kubectl get secret grafana-admin -n ${NAMESPACE} -o jsonpath='{.data.password}' | base64 -d"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

