#!/bin/bash
# 새 Worker 노드 추가 자동화 스크립트
# 용도: Terraform apply → Ansible inventory 업데이트 → 클러스터 조인
#
# 사용법:
#   ./scripts/add-worker-nodes.sh
#
# 사전 조건:
#   - terraform plan 완료 (worker-nodes.tfplan 생성)
#   - AWS credentials 설정
#   - SSH key (~/.ssh/sesacthon.pem) 존재

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"
ANSIBLE_DIR="$PROJECT_ROOT/ansible"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 새 Worker 노드 추가 시작"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Step 1: Terraform Apply (Plan 파일 있는 경우)
echo ""
echo "📦 Step 1: Terraform Apply"
echo "────────────────────────────────────────────────────────────────────────"

cd "$TERRAFORM_DIR"

if [ -f "worker-nodes.tfplan" ]; then
    echo "✅ Plan 파일 발견: worker-nodes.tfplan"
    read -p "Apply를 진행하시겠습니까? (y/n): " confirm
    if [ "$confirm" = "y" ]; then
        terraform apply "worker-nodes.tfplan"
    else
        echo "❌ Apply 취소됨"
        exit 1
    fi
else
    echo "⚠️  Plan 파일이 없습니다. 먼저 다음 명령어를 실행하세요:"
    echo ""
    echo "    cd $TERRAFORM_DIR"
    echo "    terraform plan -target=module.worker_storage_2 -target=module.worker_ai_2 -var-file=env/dev.tfvars -out=worker-nodes.tfplan"
    echo ""
    exit 1
fi

# Step 2: 새 노드 IP 가져오기
echo ""
echo "📡 Step 2: 새 노드 IP 확인"
echo "────────────────────────────────────────────────────────────────────────"

STORAGE_2_PUBLIC_IP=$(terraform output -raw worker_storage_2_public_ip 2>/dev/null || echo "")
STORAGE_2_PRIVATE_IP=$(terraform output -json cluster_info 2>/dev/null | jq -r '.worker_storage_2_private_ip // empty' || echo "")
AI_2_PUBLIC_IP=$(terraform output -raw worker_ai_2_public_ip 2>/dev/null || echo "")
AI_2_PRIVATE_IP=$(terraform output -json cluster_info 2>/dev/null | jq -r '.worker_ai_2_private_ip // empty' || echo "")

# Private IP 직접 조회 (output에 없는 경우)
if [ -z "$STORAGE_2_PRIVATE_IP" ]; then
    STORAGE_2_INSTANCE_ID=$(terraform output -raw worker_storage_2_instance_id)
    STORAGE_2_PRIVATE_IP=$(aws ec2 describe-instances --instance-ids "$STORAGE_2_INSTANCE_ID" --query 'Reservations[0].Instances[0].PrivateIpAddress' --output text)
fi

if [ -z "$AI_2_PRIVATE_IP" ]; then
    AI_2_INSTANCE_ID=$(terraform output -raw worker_ai_2_instance_id)
    AI_2_PRIVATE_IP=$(aws ec2 describe-instances --instance-ids "$AI_2_INSTANCE_ID" --query 'Reservations[0].Instances[0].PrivateIpAddress' --output text)
fi

echo "  k8s-worker-storage-2: $STORAGE_2_PUBLIC_IP (private: $STORAGE_2_PRIVATE_IP)"
echo "  k8s-worker-ai-2: $AI_2_PUBLIC_IP (private: $AI_2_PRIVATE_IP)"

if [ -z "$STORAGE_2_PUBLIC_IP" ] || [ -z "$AI_2_PUBLIC_IP" ]; then
    echo "❌ 새 노드 IP를 가져올 수 없습니다."
    exit 1
fi

# Step 3: Ansible Inventory 업데이트
echo ""
echo "📝 Step 3: Ansible Inventory 업데이트"
echo "────────────────────────────────────────────────────────────────────────"

HOSTS_FILE="$ANSIBLE_DIR/inventory/hosts.ini"

# 이미 추가되어 있는지 확인
if grep -q "k8s-worker-storage-2" "$HOSTS_FILE"; then
    echo "⚠️  k8s-worker-storage-2 이미 존재. 업데이트 중..."
    sed -i.bak "/k8s-worker-storage-2/d" "$HOSTS_FILE"
fi

if grep -q "k8s-worker-ai-2" "$HOSTS_FILE"; then
    echo "⚠️  k8s-worker-ai-2 이미 존재. 업데이트 중..."
    sed -i.bak "/k8s-worker-ai-2/d" "$HOSTS_FILE"
fi

# [workers] 그룹에 새 노드 추가
# 마지막 worker 노드 뒤에 추가
sed -i.bak "/k8s-worker-ai ansible_host/a\\
k8s-worker-storage-2 ansible_host=$STORAGE_2_PUBLIC_IP private_ip=$STORAGE_2_PRIVATE_IP workload=worker-storage worker_type=io-bound domain=scan instance_type=t3.medium phase=4\\
k8s-worker-ai-2 ansible_host=$AI_2_PUBLIC_IP private_ip=$AI_2_PRIVATE_IP workload=worker-ai worker_type=network-bound domain=scan,chat instance_type=t3.medium phase=4
" "$HOSTS_FILE"

# new_workers 그룹 추가 (없는 경우)
if ! grep -q "\[new_workers\]" "$HOSTS_FILE"; then
    echo "" >> "$HOSTS_FILE"
    echo "# New worker nodes (temporary group for join)" >> "$HOSTS_FILE"
    echo "[new_workers]" >> "$HOSTS_FILE"
    echo "k8s-worker-storage-2" >> "$HOSTS_FILE"
    echo "k8s-worker-ai-2" >> "$HOSTS_FILE"
fi

echo "✅ Inventory 업데이트 완료"
cat "$HOSTS_FILE" | grep -A 5 "\[workers\]"

# Step 4: SSH 연결 대기
echo ""
echo "⏳ Step 4: SSH 연결 대기 (최대 2분)"
echo "────────────────────────────────────────────────────────────────────────"

for ip in "$STORAGE_2_PUBLIC_IP" "$AI_2_PUBLIC_IP"; do
    echo -n "  $ip 연결 대기 중..."
    for i in {1..24}; do
        if nc -z -w 5 "$ip" 22 2>/dev/null; then
            echo " ✅"
            break
        fi
        sleep 5
        echo -n "."
    done
done

# Step 5: Ansible Playbook 실행
echo ""
echo "🔧 Step 5: Ansible Playbook 실행"
echo "────────────────────────────────────────────────────────────────────────"

cd "$ANSIBLE_DIR"

echo "실행할 명령어:"
echo "  ansible-playbook -i inventory/hosts.ini playbooks/add-worker-nodes.yml -l new_workers"
echo ""

read -p "Ansible playbook을 실행하시겠습니까? (y/n): " run_ansible
if [ "$run_ansible" = "y" ]; then
    ansible-playbook -i inventory/hosts.ini playbooks/add-worker-nodes.yml -l new_workers
else
    echo ""
    echo "수동으로 실행하려면:"
    echo "  cd $ANSIBLE_DIR"
    echo "  ansible-playbook -i inventory/hosts.ini playbooks/add-worker-nodes.yml -l new_workers"
fi

# Step 6: 결과 확인
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "노드 상태 확인:"
echo "  kubectl get nodes -o wide"
echo ""
echo "새 노드에서 워크로드 확인:"
echo "  kubectl get pods -o wide | grep -E 'worker-storage-2|worker-ai-2'"
