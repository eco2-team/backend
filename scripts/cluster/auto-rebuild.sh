#!/bin/bash
# 완전 자동 재구축 - 13-Node Architecture + v0.6.0
# 1. Terraform destroy (기존 인프라 삭제)
# 2. Terraform apply (13-Node 인프라 구축)
# 3. Ansible playbook (Kubernetes 설치)
# 4. Monitoring Stack 배포 (Prometheus/Grafana)
# 5. Worker 이미지 빌드 & 배포 (Storage/AI Workers)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🤖 완전 자동 재구축 시작 (13-Node + v0.6.0)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "⚠️  확인 프롬프트 없이 자동 실행됩니다!"
echo ""
echo "📋 실행 순서:"
echo "   1️⃣  Terraform destroy (기존 인프라 삭제)"
echo "   2️⃣  Terraform apply (13-Node 인프라 구축)"
echo "   3️⃣  Ansible playbook (Kubernetes 설치)"
echo "   4️⃣  Monitoring Stack 배포 (원격)"
echo "   5️⃣  Worker 이미지 빌드 (로컬)"
echo "   6️⃣  Worker 배포 (원격)"
echo ""
echo "⏱️  예상 소요 시간: 50-70분"
echo ""

# 환경 변수 확인
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 환경 변수 확인"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Docker 및 GHCR 인증 확인
if [ -z "$GITHUB_TOKEN" ] || [ -z "$GITHUB_USERNAME" ]; then
    echo "⚠️  경고: GITHUB_TOKEN 또는 GITHUB_USERNAME이 설정되지 않았습니다."
    echo "   Worker 이미지 빌드를 건너뛰고 진행합니다."
    echo ""
    SKIP_WORKER_BUILD=true
else
    SKIP_WORKER_BUILD=false
    echo "✅ GitHub 인증 정보 확인됨"
fi

# 버전 설정
VERSION=${VERSION:-v0.6.0}
echo "   Version: $VERSION"
echo ""

# 자동 모드 설정
export AUTO_MODE=true

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 1: Terraform Destroy
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣ Terraform Destroy - 기존 인프라 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$PROJECT_ROOT/terraform"

echo "🔧 Terraform 초기화..."
terraform init -migrate-state -upgrade
echo ""

# 기존 리소스 확인
if terraform state list >/dev/null 2>&1; then
    RESOURCE_COUNT=$(terraform state list 2>/dev/null | wc -l | tr -d ' ')
    
    if [ "$RESOURCE_COUNT" -gt 0 ]; then
        echo "📊 현재 리소스 개수: $RESOURCE_COUNT"
        echo ""
        
        # VPC ID와 AWS Region 미리 가져오기 (정리용)
        VPC_ID=$(terraform output -raw vpc_id 2>/dev/null || echo "")
        AWS_REGION=$(terraform output -raw aws_region 2>/dev/null || echo "ap-northeast-2")
        export AWS_REGION
        
        # 1단계: State에 없는 AWS 리소스 사전 정리
        if [ -n "$VPC_ID" ] && [ "$VPC_ID" != "" ]; then
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo "1-1. AWS 리소스 사전 정리 (State 외부)"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo ""
            echo "📋 VPC ID: $VPC_ID"
            echo ""
            
            # IAM Policy 정리 (State와 충돌 방지)
            echo "🔐 IAM Policy 정리..."
            POLICY_ARN=$(aws iam list-policies --scope Local --query "Policies[?PolicyName=='prod-alb-controller-policy'].Arn" --output text 2>/dev/null || echo "")
            if [ -n "$POLICY_ARN" ]; then
                echo "  ⚠️  기존 IAM Policy 발견: $POLICY_ARN"
                # Policy가 Role에 연결되어 있을 수 있으므로 일단 Skip
                echo "     (Terraform destroy에서 처리됨)"
            else
                echo "  ✅ IAM Policy 없음"
            fi
            echo ""
            
            # Load Balancer 정리 (Terraform이 모르는 ALB)
            echo "⚖️  Load Balancer 정리..."
            ALB_ARNS=$(aws elbv2 describe-load-balancers \
                --region "$AWS_REGION" \
                --query "LoadBalancers[?VpcId==\`$VPC_ID\`].LoadBalancerArn" \
                --output text 2>/dev/null || echo "")
            
            if [ -n "$ALB_ARNS" ]; then
                echo "  ⚠️  Kubernetes 생성 Load Balancer 발견:"
                for alb_arn in $ALB_ARNS; do
                    ALB_NAME=$(aws elbv2 describe-load-balancers \
                        --load-balancer-arns "$alb_arn" \
                        --region "$AWS_REGION" \
                        --query 'LoadBalancers[0].LoadBalancerName' \
                        --output text 2>/dev/null || echo "unknown")
                    echo "     - 삭제: $ALB_NAME"
                    aws elbv2 delete-load-balancer --load-balancer-arn "$alb_arn" --region "$AWS_REGION" 2>/dev/null || true
                done
                echo "  ⏳ ALB 삭제 대기 (30초)..."
                sleep 30
            else
                echo "  ✅ Load Balancer 없음"
            fi
            echo ""
            
            # Target Groups 정리
            echo "🎯 Target Groups 정리..."
            TG_ARNS=$(aws elbv2 describe-target-groups \
                --region "$AWS_REGION" \
                --query "TargetGroups[?VpcId==\`$VPC_ID\`].TargetGroupArn" \
                --output text 2>/dev/null || echo "")
            
            if [ -n "$TG_ARNS" ]; then
                echo "  ⚠️  남은 Target Groups 발견:"
                for tg_arn in $TG_ARNS; do
                    echo "     - 삭제: $(basename $tg_arn)"
                    aws elbv2 delete-target-group --target-group-arn "$tg_arn" --region "$AWS_REGION" 2>/dev/null || true
                done
                sleep 5
            else
                echo "  ✅ Target Groups 없음"
            fi
            echo ""
            
            # Security Groups 규칙 정리 (순환 참조 해결)
            echo "🔒 Security Groups 규칙 정리..."
            TERRAFORM_SGS=$(aws ec2 describe-security-groups \
                --filters "Name=vpc-id,Values=$VPC_ID" "Name=group-name,Values=prod-k8s-*" \
                --region "$AWS_REGION" \
                --query 'SecurityGroups[*].GroupId' \
                --output text 2>/dev/null || echo "")
            
            if [ -n "$TERRAFORM_SGS" ]; then
                echo "  ⚠️  Terraform Security Groups 발견, 규칙 정리 중..."
                for sg in $TERRAFORM_SGS; do
                    # Ingress 규칙 삭제
                    INGRESS_RULES=$(aws ec2 describe-security-group-rules \
                        --group-ids "$sg" \
                        --region "$AWS_REGION" \
                        --query 'SecurityGroupRules[?IsEgress==`false`].SecurityGroupRuleId' \
                        --output text 2>/dev/null || echo "")
                    
                    if [ -n "$INGRESS_RULES" ]; then
                        for rule_id in $INGRESS_RULES; do
                            aws ec2 revoke-security-group-ingress \
                                --group-id "$sg" \
                                --security-group-rule-ids "$rule_id" \
                                --region "$AWS_REGION" 2>/dev/null || true
                        done
                    fi
                    
                    # Egress 규칙 삭제
                    EGRESS_RULES=$(aws ec2 describe-security-group-rules \
                        --group-ids "$sg" \
                        --region "$AWS_REGION" \
                        --query 'SecurityGroupRules[?IsEgress==`true`].SecurityGroupRuleId' \
                        --output text 2>/dev/null || echo "")
                    
                    if [ -n "$EGRESS_RULES" ]; then
                        for rule_id in $EGRESS_RULES; do
                            aws ec2 revoke-security-group-egress \
                                --group-id "$sg" \
                                --security-group-rule-ids "$rule_id" \
                                --region "$AWS_REGION" 2>/dev/null || true
                        done
                    fi
                done
                echo "  ✅ Security Groups 규칙 정리 완료"
                sleep 5
            else
                echo "  ✅ Terraform Security Groups 없음"
            fi
            echo ""
        fi
        
        # 2단계: Terraform Destroy 실행
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "1-2. Terraform Destroy 실행"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "🗑️  Terraform destroy 실행..."
        
        set +e  # destroy 실패해도 계속 진행
        terraform destroy -auto-approve
        DESTROY_EXIT_CODE=$?
        set -e
        
        if [ $DESTROY_EXIT_CODE -ne 0 ]; then
            echo ""
            echo "⚠️  Terraform destroy 실패 (exit code: $DESTROY_EXIT_CODE)"
            echo "   일부 리소스가 수동으로 import되거나 남아있을 수 있습니다."
            echo ""
            
            # 실패 시 남은 리소스 정리 시도
            if [ -n "$VPC_ID" ] && [ "$VPC_ID" != "" ]; then
                echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                echo "1-3. 남은 AWS 리소스 강제 정리"
                echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                echo ""
                
                # S3 Bucket 정리
                echo "🪣 S3 Bucket 정리..."
                BUCKETS=$(aws s3api list-buckets --query "Buckets[?starts_with(Name, 'prod-sesacthon')].Name" --output text 2>/dev/null || echo "")
                if [ -n "$BUCKETS" ]; then
                    for bucket in $BUCKETS; do
                        echo "  - 삭제: $bucket"
                        aws s3 rm "s3://$bucket" --recursive 2>/dev/null || true
                        aws s3api delete-bucket --bucket "$bucket" --region "$AWS_REGION" 2>/dev/null || true
                    done
                else
                    echo "  ✅ S3 Bucket 없음"
                fi
                echo ""
                
                # Key Pair 정리
                echo "🔑 Key Pair 정리..."
                KEY_NAME="k8s-cluster-key"
                if aws ec2 describe-key-pairs --key-names "$KEY_NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
                    echo "  - 삭제: $KEY_NAME"
                    aws ec2 delete-key-pair --key-name "$KEY_NAME" --region "$AWS_REGION" 2>/dev/null || true
                else
                    echo "  ✅ Key Pair 없음"
                fi
                echo ""
                
                # IAM Policy 정리 (Role detach 후 삭제)
                echo "🔐 IAM Policy 강제 정리..."
                POLICY_ARN=$(aws iam list-policies --scope Local --query "Policies[?PolicyName=='prod-alb-controller-policy'].Arn" --output text 2>/dev/null || echo "")
                if [ -n "$POLICY_ARN" ]; then
                    echo "  - 발견: $POLICY_ARN"
                    
                    # Role에서 detach
                    ATTACHED_ROLES=$(aws iam list-entities-for-policy --policy-arn "$POLICY_ARN" --entity-filter Role --query 'PolicyRoles[*].RoleName' --output text 2>/dev/null || echo "")
                    if [ -n "$ATTACHED_ROLES" ]; then
                        for role in $ATTACHED_ROLES; do
                            echo "    - Role에서 분리: $role"
                            aws iam detach-role-policy --role-name "$role" --policy-arn "$POLICY_ARN" 2>/dev/null || true
                        done
                    fi
                    
                    # Policy 삭제
                    echo "    - Policy 삭제"
                    aws iam delete-policy --policy-arn "$POLICY_ARN" 2>/dev/null || true
                else
                    echo "  ✅ IAM Policy 없음"
                fi
                echo ""
            fi
        else
            echo "✅ 기존 인프라 삭제 완료"
        fi
        
        # AWS 리소스 완전 삭제 대기
        echo ""
        echo "⏳ AWS 리소스 완전 삭제 대기 (30초)..."
        sleep 30
    else
        echo "ℹ️  삭제할 기존 인프라가 없습니다."
    fi
else
    echo "ℹ️  State 파일이 없습니다. 새로운 배포입니다."
fi

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 2: Terraform Apply (13-Node)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣ Terraform Apply - 13-Node 인프라 구축"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "📋 13-Node 구성:"
echo "   - Master: 1 (t3a.large)"
echo "   - API: 6 (t3a.medium)"
echo "   - Worker: 2 (t3a.large)"
echo "   - Infrastructure: 4 (t3a.medium)"
echo ""

echo "🔧 Terraform 초기화 (재확인)..."
terraform init -migrate-state -upgrade
echo ""

echo "🚀 Terraform apply 실행..."
terraform apply -auto-approve

if [ $? -ne 0 ]; then
    echo "❌ Terraform apply 실패!"
    exit 1
fi

echo "✅ 13-Node 인프라 생성 완료"
echo ""

# 인스턴스 정보 출력
echo "📋 생성된 인스턴스 정보:"
terraform output -json | jq -r '
  "Master: " + (.master_public_ip.value // "N/A"),
  "API Nodes: " + ((.api_nodes_public_ips.value // []) | length | tostring) + " nodes",
  "Worker Nodes: " + ((.worker_nodes_public_ips.value // []) | length | tostring) + " nodes",
  "Infrastructure Nodes: " + ((.infra_nodes_public_ips.value // []) | length | tostring) + " nodes"
' 2>/dev/null || echo "  (인스턴스 정보 확인 중...)"
echo ""

# Master IP 저장 (나중에 사용)
MASTER_IP=$(terraform output -raw master_public_ip 2>/dev/null || echo "")
VPC_ID=$(terraform output -raw vpc_id 2>/dev/null || echo "")
ACM_ARN=$(terraform output -raw acm_certificate_arn 2>/dev/null || echo "")

echo "  Master IP: $MASTER_IP"
echo "  VPC ID: $VPC_ID"
echo ""

# SSM Agent 등록 대기
echo "⏳ SSM Agent 등록 및 초기화 대기 (90초)..."
sleep 90
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 3: Ansible Playbook
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣ Ansible Playbook - Kubernetes 설치"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Ansible Inventory 생성
echo "📝 Ansible inventory 생성 중..."
terraform output -raw ansible_inventory > "$PROJECT_ROOT/ansible/inventory/hosts.ini"

if [ $? -ne 0 ]; then
    echo "❌ Inventory 생성 실패!"
    exit 1
fi

echo "✅ Inventory 생성 완료"
echo ""

# Ansible 실행
cd "$PROJECT_ROOT/ansible"

echo "🚀 Ansible playbook 실행..."
ansible-playbook -i inventory/hosts.ini site.yml \
    -e "vpc_id=$VPC_ID" \
    -e "acm_certificate_arn=$ACM_ARN"

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Ansible playbook 실패!"
    echo ""
    echo "디버깅 명령어:"
    echo "  ssh ubuntu@$MASTER_IP"
    echo "  kubectl get nodes"
    echo "  kubectl get pods -A"
    exit 1
fi

echo "✅ Kubernetes 설치 완료"
echo ""

# 클러스터 상태 확인 대기
echo "⏳ 클러스터 초기화 대기 (60초)..."
sleep 60
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 4: Monitoring Stack 배포 (원격)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣ Monitoring Stack 배포 (Prometheus/Grafana)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ -z "$MASTER_IP" ]; then
    echo "❌ Master IP를 찾을 수 없습니다. 모니터링 배포를 건너뜁니다."
else
    echo "📦 모니터링 파일 복사 중..."
    
    # k8s/monitoring 디렉토리 복사
    scp -r "$PROJECT_ROOT/k8s/monitoring" ubuntu@$MASTER_IP:~/
    
    # deploy-monitoring.sh 복사
    scp "$PROJECT_ROOT/scripts/deploy-monitoring.sh" ubuntu@$MASTER_IP:~/
    
    echo "✅ 파일 복사 완료"
    echo ""
    
    echo "🚀 원격으로 모니터링 배포 실행..."
    ssh ubuntu@$MASTER_IP << 'ENDSSH'
        # Node Exporter 배포
        echo "📊 Node Exporter 배포..."
        kubectl apply -f ~/monitoring/node-exporter.yaml
        
        # Prometheus Rules ConfigMap 생성
        echo "📊 Prometheus Rules 생성..."
        kubectl create configmap prometheus-rules \
            --from-file=~/monitoring/prometheus-rules.yaml \
            --namespace=default \
            --dry-run=client -o yaml | kubectl apply -f -
        
        # Prometheus 배포
        echo "📊 Prometheus 배포..."
        kubectl apply -f ~/monitoring/prometheus-deployment.yaml
        
        # Grafana Dashboards ConfigMap 생성
        echo "📊 Grafana Dashboards 생성..."
        kubectl create configmap grafana-dashboards \
            --from-file=~/monitoring/grafana-dashboard-13nodes.json \
            --namespace=default \
            --dry-run=client -o yaml | kubectl apply -f -
        
        # Grafana 배포
        echo "📊 Grafana 배포..."
        kubectl apply -f ~/monitoring/grafana-deployment.yaml
        
        echo ""
        echo "✅ 모니터링 스택 배포 완료"
        
        # 상태 확인
        echo ""
        echo "📊 배포 상태:"
        kubectl get pods -l component=monitoring
ENDSSH
    
    if [ $? -eq 0 ]; then
        echo "✅ 모니터링 배포 성공"
    else
        echo "⚠️  모니터링 배포 실패 (계속 진행)"
    fi
fi

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 5: Worker 이미지 빌드 (로컬)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5️⃣ Worker 이미지 빌드 (로컬)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$PROJECT_ROOT"

if [ "$SKIP_WORKER_BUILD" = true ]; then
    echo "⚠️  GitHub 인증 정보가 없어 Worker 빌드를 건너뜁니다."
    echo ""
    echo "수동으로 실행하려면:"
    echo "  export GITHUB_TOKEN=<your-token>"
    echo "  export GITHUB_USERNAME=<your-username>"
    echo "  export VERSION=$VERSION"
    echo "  ./scripts/build-workers.sh"
    echo ""
else
    echo "🐳 GHCR 로그인..."
    echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$GITHUB_USERNAME" --password-stdin
    
    if [ $? -ne 0 ]; then
        echo "❌ GHCR 로그인 실패. Worker 빌드를 건너뜁니다."
        SKIP_WORKER_BUILD=true
    else
        echo "✅ GHCR 로그인 성공"
        echo ""
        
        echo "🔨 Worker 이미지 빌드..."
        export VERSION=$VERSION
        ./scripts/build-workers.sh
        
        if [ $? -eq 0 ]; then
            echo "✅ Worker 이미지 빌드 및 푸시 완료"
        else
            echo "❌ Worker 이미지 빌드 실패"
            SKIP_WORKER_BUILD=true
        fi
    fi
fi

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Step 6: Worker 배포 (원격)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6️⃣ Worker 배포 (원격)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ "$SKIP_WORKER_BUILD" = true ]; then
    echo "⚠️  Worker 이미지가 빌드되지 않아 배포를 건너뜁니다."
    echo ""
elif [ -z "$MASTER_IP" ]; then
    echo "❌ Master IP를 찾을 수 없습니다. Worker 배포를 건너뜁니다."
else
    echo "📦 Worker 설정 파일 복사 중..."
    
    # k8s/workers 디렉토리 복사
    scp -r "$PROJECT_ROOT/k8s/workers" ubuntu@$MASTER_IP:~/
    
    echo "✅ 파일 복사 완료"
    echo ""
    
    echo "🚀 원격으로 Worker 배포 실행..."
    ssh ubuntu@$MASTER_IP << ENDSSH
        # Worker 배포
        echo "📦 Worker 배포..."
        kubectl apply -f ~/workers/worker-wal-deployments.yaml
        
        echo ""
        echo "✅ Worker 배포 완료"
        
        # 상태 확인
        echo ""
        echo "📊 배포 상태:"
        kubectl get pods -l component=worker
        kubectl get pvc -l component=wal
ENDSSH
    
    if [ $? -eq 0 ]; then
        echo "✅ Worker 배포 성공"
    else
        echo "⚠️  Worker 배포 실패"
    fi
fi

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 완료 요약
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 자동 재구축 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "📊 배포 결과:"
echo "  ✅ 13-Node Kubernetes 클러스터"
echo "  ✅ Prometheus/Grafana 모니터링"
if [ "$SKIP_WORKER_BUILD" = false ]; then
    echo "  ✅ Storage/AI Workers with WAL"
else
    echo "  ⚠️  Workers (수동 배포 필요)"
fi
echo ""

echo "🔍 클러스터 확인:"
if [ -n "$MASTER_IP" ]; then
    echo "  ssh ubuntu@$MASTER_IP"
    echo "  kubectl get nodes -o wide"
    echo "  kubectl get pods -A"
    echo ""
    echo "📊 모니터링 접속:"
    echo "  Prometheus: kubectl port-forward svc/prometheus 9090:9090"
    echo "  Grafana: kubectl port-forward svc/grafana 3000:3000"
    echo ""
    echo "Grafana 비밀번호 확인:"
    echo "  kubectl get secret grafana-admin -o jsonpath='{.data.password}' | base64 -d"
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
