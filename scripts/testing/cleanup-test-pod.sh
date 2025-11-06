#!/bin/bash
# 테스트 파드 삭제 스크립트

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🗑️  테스트 리소스 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ssh -i ~/.ssh/sesacthon ubuntu@52.79.238.50 'bash -s' <<'ENDSSH'

echo "1. 테스트 Deployment 삭제..."
kubectl delete deployment test-app

echo ""
echo "2. 테스트 Service 삭제..."
kubectl delete service test-app

echo ""
echo "3. 테스트 ConfigMap 삭제..."
kubectl delete configmap test-html

echo ""
echo "4. API Ingress를 default-backend로 복원..."
kubectl apply -f - <<'EOF'
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-ingress
  namespace: default
  annotations:
    kubernetes.io/ingress.class: alb
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}, {"HTTPS": 443}]'
    alb.ingress.kubernetes.io/ssl-redirect: '443'
    alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:ap-northeast-2:721622471953:certificate/6e2ae21f-a345-4316-b151-376bdd9e121a
    alb.ingress.kubernetes.io/group.name: growbin-alb
    alb.ingress.kubernetes.io/group.order: '30'
spec:
  rules:
  - host: growbin.app
    http:
      paths:
      - path: /api/v1
        pathType: Prefix
        backend:
          service:
            name: default-backend
            port:
              number: 80
      - path: /
        pathType: Prefix
        backend:
          service:
            name: default-backend
            port:
              number: 80
EOF

echo ""
echo "5. 남은 리소스 확인..."
kubectl get deployment,service,configmap,ingress -n default

echo ""
echo "✅ 테스트 리소스 삭제 완료!"
echo ""
echo "현재 남아있는 Ingress:"
echo "  • /argocd → ArgoCD"
echo "  • /grafana → Grafana"
echo "  • / → Default Backend (404)"

ENDSSH

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

