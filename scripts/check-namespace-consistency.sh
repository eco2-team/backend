#!/bin/bash
# check-namespace-consistency.sh
# 네임스페이스 일관성 점검 스크립트

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 네임스페이스 일관성 점검 시작"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

ERRORS=0

# 1. Kustomize Overlay 점검
echo ""
echo "✅ Layer 2: Kustomize Overlays 점검"
echo "---"

for domain in auth my scan character location info chat; do
    echo -n "  $domain overlay... "
    
    # 네임스페이스 확인
    NS=$(grep "^namespace:" k8s/overlays/$domain/kustomization.yaml | awk '{print $2}')
    if [ "$NS" != "$domain" ]; then
        echo "❌ FAIL: namespace mismatch (expected: $domain, got: $NS)"
        ((ERRORS++))
    else
        echo "✅ OK"
    fi
    
    # 데이터베이스 연결 문자열 확인
    if grep -q "\.db\.svc\.cluster\.local" k8s/overlays/$domain/deployment-patch.yaml 2>/dev/null; then
        echo "  ❌ FAIL: deployment-patch.yaml에서 'db' 네임스페이스 발견 (data 또는 messaging이어야 함)"
        ((ERRORS++))
    fi
done

# 2. ArgoCD ApplicationSet 점검
echo ""
echo "✅ Layer 3: ArgoCD ApplicationSet 점검"
echo "---"

echo -n "  tier 레이블... "
if grep -q "tier: api" argocd/applications/ecoeco-appset-kustomize.yaml; then
    echo "❌ FAIL: 'tier: api' 발견 (business-logic이어야 함)"
    ((ERRORS++))
else
    echo "✅ OK"
fi

# 3. Ansible 변수 점검
echo ""
echo "✅ Layer 4: Ansible 변수 점검"
echo "---"

ANSIBLE_VARS="ansible/inventory/group_vars/all.yml"
if [ ! -f "$ANSIBLE_VARS" ]; then
    ANSIBLE_VARS="terraform/group_vars/all.yml"
fi

echo -n "  postgres_namespace... "
PG_NS=$(grep "^postgres_namespace:" $ANSIBLE_VARS | awk '{print $2}' | tr -d '"')
if [ "$PG_NS" != "data" ]; then
    echo "❌ FAIL: expected 'data', got '$PG_NS'"
    ((ERRORS++))
else
    echo "✅ OK"
fi

echo -n "  redis_namespace... "
REDIS_NS=$(grep "^redis_namespace:" $ANSIBLE_VARS | awk '{print $2}' | tr -d '"')
if [ "$REDIS_NS" != "data" ]; then
    echo "❌ FAIL: expected 'data', got '$REDIS_NS'"
    ((ERRORS++))
else
    echo "✅ OK"
fi

echo -n "  rabbitmq_namespace... "
RABBITMQ_NS=$(grep "^rabbitmq_namespace:" $ANSIBLE_VARS | awk '{print $2}' | tr -d '"')
if [ "$RABBITMQ_NS" != "messaging" ]; then
    echo "❌ FAIL: expected 'messaging', got '$RABBITMQ_NS'"
    ((ERRORS++))
else
    echo "✅ OK"
fi

# 4. NetworkPolicy 점검
echo ""
echo "✅ Layer 1: NetworkPolicy 점검"
echo "---"

echo -n "  data-ingress-from-api... "
if grep -A 5 "data-ingress-from-api" k8s/networkpolicies/domain-isolation.yaml | grep -q "tier: api"; then
    echo "❌ FAIL: 'tier: api' 발견 (business-logic이어야 함)"
    ((ERRORS++))
else
    echo "✅ OK"
fi

# 5. ServiceMonitor 점검
echo ""
echo "✅ Layer 1: ServiceMonitor 점검"
echo "---"

echo -n "  api-services-all-domains... "
if grep -A 10 "api-services-all-domains" k8s/monitoring/servicemonitors-domain-ns.yaml | grep -q "tier: api"; then
    echo "❌ FAIL: 'tier: api' 발견 (business-logic이어야 함)"
    ((ERRORS++))
else
    echo "✅ OK"
fi

# 6. Ingress 점검 (추가)
echo ""
echo "✅ Layer 3: Ingress 점검"
echo "---"

echo -n "  domain-based-api-ingress.yaml 파일... "
if [ ! -f "k8s/ingress/domain-based-api-ingress.yaml" ]; then
    echo "❌ FAIL: domain-based-api-ingress.yaml 파일이 없음"
    ((ERRORS++))
else
    echo "✅ OK"
fi

echo -n "  infrastructure-ingress.yaml 파일... "
if [ ! -f "k8s/ingress/infrastructure-ingress.yaml" ]; then
    echo "❌ FAIL: infrastructure-ingress.yaml 파일이 없음"
    ((ERRORS++))
else
    echo "✅ OK"
fi

echo -n "  Ingress 네임스페이스 일치... "
# auth-ingress가 auth 네임스페이스에 있는지 확인
if grep -A 5 "name: auth-ingress" k8s/ingress/domain-based-api-ingress.yaml | grep -q "namespace: auth"; then
    echo "✅ OK"
else
    echo "❌ FAIL: auth-ingress가 auth 네임스페이스에 없음"
    ((ERRORS++))
fi

echo -n "  ALB Group 일관성... "
# 모든 Ingress가 ecoeco-main 그룹 사용 확인
ALB_GROUP_COUNT=$(grep -r "alb.ingress.kubernetes.io/group.name:" k8s/ingress/*.yaml | grep -v "ecoeco-main" | wc -l)
if [ "$ALB_GROUP_COUNT" -gt 0 ]; then
    echo "❌ FAIL: ecoeco-main이 아닌 ALB Group 발견"
    ((ERRORS++))
else
    echo "✅ OK"
fi

# 7. Secret 점검 (추가)
echo ""
echo "✅ Layer 4: Secret 일관성 점검"
echo "---"

echo -n "  PostgreSQL Secret 이름... "
if grep -q "postgresql-secret" ansible/roles/postgresql/tasks/main.yml; then
    echo "✅ OK (postgresql-secret)"
elif grep -q "postgres-secret" ansible/roles/postgresql/tasks/main.yml; then
    echo "❌ FAIL: 'postgres-secret' 사용 (postgresql-secret이어야 함)"
    ((ERRORS++))
else
    echo "⚠️  WARNING: Secret 생성 태스크를 찾을 수 없음"
fi

echo -n "  AWS Credentials 스크립트... "
if [ -f "scripts/create-aws-credentials-secret.sh" ] && [ -x "scripts/create-aws-credentials-secret.sh" ]; then
    echo "✅ OK"
else
    echo "❌ FAIL: create-aws-credentials-secret.sh가 없거나 실행 권한 없음"
    ((ERRORS++))
fi

# 8. Ansible Playbook 점검 (추가)
echo ""
echo "✅ Layer 4: Ansible Playbook 점검"
echo "---"

echo -n "  api 네임스페이스 생성 제거... "
if grep -q "kubectl create namespace api" ansible/playbooks/07-ingress-resources.yml; then
    echo "❌ FAIL: api 네임스페이스 생성 태스크 발견 (제거해야 함)"
    ((ERRORS++))
else
    echo "✅ OK"
fi

echo -n "  domain-based Ingress 적용... "
if grep -q "domain-based-api-ingress.yaml" ansible/playbooks/07-ingress-resources.yml; then
    echo "✅ OK"
else
    echo "❌ FAIL: domain-based-api-ingress.yaml 적용 태스크 없음"
    ((ERRORS++))
fi

# 9. Terraform 템플릿 점검 (추가)
echo ""
echo "✅ Layer 5: Terraform 템플릿 점검"
echo "---"

echo -n "  hosts.tpl [api_nodes] 중복... "
API_NODES_COUNT=$(grep -c "^\[api_nodes\]" terraform/templates/hosts.tpl)
if [ "$API_NODES_COUNT" -gt 1 ]; then
    echo "❌ FAIL: [api_nodes] 섹션이 $API_NODES_COUNT 번 나타남 (1번이어야 함)"
    ((ERRORS++))
else
    echo "✅ OK (1번)"
fi

echo -n "  hosts.tpl 제거된 노드 참조... "
DEPRECATED_NODES="api_waste|api_userinfo|api_recycle_info|api_chat_llm"
if grep -E "$DEPRECATED_NODES" terraform/templates/hosts.tpl > /dev/null 2>&1; then
    echo "❌ FAIL: 제거된 노드 참조 발견"
    grep -E "$DEPRECATED_NODES" terraform/templates/hosts.tpl
    ((ERRORS++))
else
    echo "✅ OK"
fi

echo -n "  outputs.tf 변수 개수... "
API_VAR_COUNT=$(grep -E "api_.*_public_ip\s*=" terraform/outputs.tf | wc -l | tr -d ' ')
EXPECTED_COUNT=7  # 7 API nodes (public_ip만 카운트)
if [ "$API_VAR_COUNT" -ne "$EXPECTED_COUNT" ]; then
    echo "❌ FAIL: API 노드 변수 개수 불일치 (expected: $EXPECTED_COUNT, got: $API_VAR_COUNT)"
    ((ERRORS++))
else
    echo "✅ OK ($EXPECTED_COUNT API nodes)"
fi

# 최종 결과
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $ERRORS -eq 0 ]; then
    echo "✅ 모든 점검 통과! 네임스페이스 일관성 확인 완료."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 0
else
    echo "❌ $ERRORS개 오류 발견! 위 내용을 확인하고 수정하세요."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 1
fi

