#!/bin/bash

# 각 namespace의 Pod IP를 자동으로 가져와서 Endpoints 생성

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     Service & Endpoints 자동 생성 스크립트                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

SERVICES=("auth" "my" "scan" "character" "location" "info" "chat")

for svc in "${SERVICES[@]}"; do
    echo "Processing $svc-api..."

    # Pod IP 가져오기
    POD_IP=$(kubectl get pods -n $svc -l app=${svc}-api -o jsonpath='{.items[0].status.podIP}' 2>/dev/null)

    if [ -z "$POD_IP" ]; then
        echo "  ⚠️  No pod found for $svc, skipping..."
        continue
    fi

    echo "  Pod IP: $POD_IP"

    # Headless Service 생성
    kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: ${svc}-api
  namespace: default
spec:
  type: ClusterIP
  clusterIP: None
  ports:
    - port: 8000
      targetPort: 8000
      protocol: TCP
      name: http
EOF

    # Endpoints 생성
    kubectl apply -f - <<EOF
apiVersion: v1
kind: Endpoints
metadata:
  name: ${svc}-api
  namespace: default
subsets:
  - addresses:
      - ip: $POD_IP
    ports:
      - port: 8000
        protocol: TCP
        name: http
EOF

    echo "  ✅ ${svc}-api service and endpoint created"
    echo ""
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 완료!"
echo ""
echo "확인:"
kubectl get svc,endpoints -n default | grep api
echo ""
echo "Ingress 재시작:"
echo "kubectl delete ingress api-ingress -n default"
echo "kubectl apply -k workloads/ingress/dev"
