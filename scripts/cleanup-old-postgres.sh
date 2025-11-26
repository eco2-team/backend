#!/bin/bash
# 기존 PostgreSQL 리소스 완전 삭제 스크립트

set -e

echo "🗑️  기존 PostgreSQL 리소스 삭제 시작..."

# 1. Zalando Postgres Operator CR 삭제
echo "1️⃣  PostgreSQL Custom Resource 삭제..."
kubectl -n postgres delete postgresql postgres-cluster --ignore-not-found=true --wait=false

# 2. StatefulSet 강제 삭제
echo "2️⃣  StatefulSet 삭제..."
kubectl -n postgres delete statefulset postgres-cluster --ignore-not-found=true --wait=false

# 3. Pod 강제 삭제
echo "3️⃣  Pod 삭제..."
kubectl -n postgres delete pod -l application=spilo,cluster-name=postgres-cluster --ignore-not-found=true --grace-period=0 --force

# 4. Services 삭제
echo "4️⃣  Services 삭제..."
kubectl -n postgres delete service postgres-cluster --ignore-not-found=true
kubectl -n postgres delete service postgres-cluster-repl --ignore-not-found=true
kubectl -n postgres delete service postgres-cluster-config --ignore-not-found=true

# 5. PVC 삭제 (선택적 - 데이터 완전 삭제)
echo "5️⃣  PVC 삭제 (데이터 완전 삭제)..."
read -p "⚠️  PVC를 삭제하시겠습니까? 데이터가 완전히 삭제됩니다! (yes/no): " confirm
if [ "$confirm" = "yes" ]; then
    kubectl -n postgres delete pvc -l application=spilo,cluster-name=postgres-cluster --ignore-not-found=true
    echo "✅ PVC 삭제 완료"
else
    echo "⏭️  PVC 삭제 건너뜀 (수동으로 삭제 필요: kubectl -n postgres delete pvc pgdata-postgres-cluster-0)"
fi

# 6. ConfigMap/Secret 정리
echo "6️⃣  ConfigMap/Secret 정리..."
kubectl -n postgres delete configmap -l application=spilo,cluster-name=postgres-cluster --ignore-not-found=true
kubectl -n postgres delete secret -l application=spilo,cluster-name=postgres-cluster --ignore-not-found=true

# 7. Postgres Operator 제거 (선택적)
echo "7️⃣  Postgres Operator 제거..."
kubectl -n data-system delete deployment postgres-operator --ignore-not-found=true

# 8. 남아있는 리소스 확인
echo ""
echo "📊 현재 postgres namespace 리소스 확인:"
kubectl -n postgres get all

echo ""
echo "✅ 기존 PostgreSQL 리소스 삭제 완료!"
echo "이제 새로운 Bitnami PostgreSQL Helm Chart를 배포할 수 있습니다."
