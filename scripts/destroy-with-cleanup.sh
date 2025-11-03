#!/bin/bash
# 인프라 및 구성요소 완전 삭제 스크립트 (Cleanup)
# Kubernetes 리소스 정리 → AWS 리소스 정리 → Terraform 삭제
# VPC 삭제 장시간 대기 문제 해결

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🧹 인프라 및 구성요소 삭제 (Cleanup)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "⚠️  이 스크립트는 다음을 삭제합니다:"
echo "   1. Kubernetes 리소스 (Ingress, PVC, Helm Releases)"
echo "   2. Kubernetes가 생성한 AWS 리소스 (EBS 볼륨, 보안 그룹)"
echo "   3. Terraform 인프라 (EC2, VPC, 모든 리소스)"
echo ""

# 자동 모드 확인 (AUTO_MODE 환경 변수로 제어)
AUTO_MODE=${AUTO_MODE:-false}

if [ "$AUTO_MODE" != "true" ]; then
    # 확인 프롬프트
    read -p "⚠️  정말로 모든 리소스를 삭제하시겠습니까? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "❌ 취소되었습니다."
        exit 0
    fi
else
    echo "🤖 자동 모드로 실행 중..."
    echo "   확인 프롬프트 없이 자동 삭제합니다."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣ Kubernetes 리소스 정리"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# kubeconfig 확인
if ! kubectl cluster-info &>/dev/null; then
    echo "⚠️  Kubernetes 클러스터에 연결할 수 없습니다."
    echo "   클러스터가 이미 삭제되었거나 접근 권한이 없습니다."
    echo "   Kubernetes 리소스 정리를 건너뜁니다."
    echo ""
    SKIP_K8S_CLEANUP=true
else
    SKIP_K8S_CLEANUP=false
    
    echo "📋 클러스터 정보:"
    kubectl cluster-info | head -1
    echo ""
    
    # 1. Ingress 삭제 (ALB 및 보안 그룹 제거)
    echo "🗑️  Ingress 리소스 삭제 중..."
    kubectl delete ingress --all -A 2>/dev/null || echo "  (Ingress 없음 또는 이미 삭제됨)"
    
    # 2. Service type=LoadBalancer 삭제 (ALB 제거)
    echo "🗑️  LoadBalancer 타입 Service 삭제 중..."
    kubectl get svc -A -o json | jq -r '.items[] | select(.spec.type=="LoadBalancer") | "\(.metadata.namespace)/\(.metadata.name)"' | \
        while read ns name; do
            echo "  - 삭제: $ns/$name"
            kubectl delete svc "$name" -n "$ns" 2>/dev/null || true
        done || echo "  (LoadBalancer Service 없음)"
    
    # 3. PVC 삭제 (EBS 볼륨 제거)
    echo "🗑️  PVC 삭제 중..."
    kubectl delete pvc --all -A 2>/dev/null || echo "  (PVC 없음 또는 이미 삭제됨)"
    
    # 4. Helm Release 삭제
    echo "🗑️  Helm Release 삭제 중..."
    
    # Monitoring
    if helm list -n monitoring 2>/dev/null | grep -q .; then
        echo "  - Monitoring (Prometheus, Grafana) 삭제 중..."
        helm uninstall kube-prometheus-stack -n monitoring 2>/dev/null || true
        helm uninstall prometheus -n monitoring 2>/dev/null || true
        helm uninstall grafana -n monitoring 2>/dev/null || true
    fi
    
    # RabbitMQ (Operator 관리 - RabbitmqCluster CR 삭제)
    if kubectl get rabbitmqcluster rabbitmq -n messaging >/dev/null 2>&1; then
        echo "  - RabbitMQ Cluster CR 삭제 중..."
        kubectl delete rabbitmqcluster rabbitmq -n messaging 2>/dev/null || true
        # RabbitMQ Operator는 유지 (CRD 유지)
    fi
    
    # ArgoCD
    if helm list -n argocd 2>/dev/null | grep -q .; then
        echo "  - ArgoCD 삭제 중..."
        helm uninstall argocd -n argocd 2>/dev/null || true
    fi
    
    # ALB Controller
    if helm list -n kube-system 2>/dev/null | grep -q aws-load-balancer-controller; then
        echo "  - AWS Load Balancer Controller 삭제 중..."
        helm uninstall aws-load-balancer-controller -n kube-system 2>/dev/null || true
    fi
    
    # 기타 모든 Helm Release 삭제
    echo "  - 기타 Helm Release 삭제 중..."
    helm list -A -o json 2>/dev/null | jq -r '.[] | "\(.namespace)/\(.name)"' | \
        while read ns name; do
            echo "    - 삭제: $ns/$name"
            helm uninstall "$name" -n "$ns" 2>/dev/null || true
        done || true
    
    echo ""
    echo "⏳ Kubernetes 리소스 정리 대기 (30초)..."
    sleep 30
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣ AWS 리소스 확인 및 정리"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$TERRAFORM_DIR"

# Terraform backend 초기화
if [ -f "terraform.tfstate" ] || [ -d ".terraform" ]; then
    echo "🔧 Terraform backend 확인..."
    terraform init -migrate-state -upgrade -input=false >/dev/null 2>&1 || true
    echo ""
    
    # VPC ID 가져오기
    VPC_ID=$(terraform output -raw vpc_id 2>/dev/null || echo "")
    
    if [ -n "$VPC_ID" ] && [ "$VPC_ID" != "" ]; then
        echo "📋 VPC ID: $VPC_ID"
        echo ""
        
        # AWS Region 가져오기
        AWS_REGION=$(terraform output -raw aws_region 2>/dev/null || echo "ap-northeast-2")
        export AWS_REGION
        
        echo "🔍 Kubernetes가 생성한 AWS 리소스 확인 중..."
        echo ""
        
        # 1. EBS 볼륨 확인 및 삭제
        echo "💾 EBS 볼륨 확인..."
        VOLUMES=$(aws ec2 describe-volumes \
            --filters "Name=tag-key,Values=kubernetes.io/created-for/pvc/name" \
            --region "$AWS_REGION" \
            --query 'Volumes[?State==`available`].VolumeId' \
            --output text 2>/dev/null || echo "")
        
        if [ -n "$VOLUMES" ]; then
            echo "⚠️  남은 EBS 볼륨 발견:"
            for vol in $VOLUMES; do
                SIZE=$(aws ec2 describe-volumes --volume-ids "$vol" --region "$AWS_REGION" \
                    --query 'Volumes[0].Size' --output text 2>/dev/null || echo "?")
                echo "  - 삭제: $vol (${SIZE}GB)"
                aws ec2 delete-volume --volume-id "$vol" --region "$AWS_REGION" 2>/dev/null || true
            done
        else
            echo "  ✅ EBS 볼륨 없음"
        fi
        echo ""
        
        # 2. 보안 그룹 확인 및 삭제 (k8s-* 패턴)
        echo "🔒 Kubernetes 생성 보안 그룹 확인..."
        SG_IDS=$(aws ec2 describe-security-groups \
            --filters "Name=vpc-id,Values=$VPC_ID" "Name=group-name,Values=k8s-*" \
            --region "$AWS_REGION" \
            --query 'SecurityGroups[*].GroupId' \
            --output text 2>/dev/null || echo "")
        
        if [ -n "$SG_IDS" ]; then
            echo "⚠️  Kubernetes 생성 보안 그룹 발견:"
            for sg in $SG_IDS; do
                SG_NAME=$(aws ec2 describe-security-groups --group-ids "$sg" --region "$AWS_REGION" \
                    --query 'SecurityGroups[0].GroupName' --output text 2>/dev/null || echo "?")
                echo "  - 삭제 시도: $sg ($SG_NAME)"
                
                # 보안 그룹 직접 삭제 시도 (AWS가 자동으로 규칙 정리)
                if aws ec2 delete-security-group --group-id "$sg" --region "$AWS_REGION" 2>/dev/null; then
                    echo "    ✅ 삭제 성공"
                else
                    # 실패 시 규칙 수동 정리 후 재시도
                    echo "    ⚠️  직접 삭제 실패, 규칙 정리 중..."
                    
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
                    
                    # 재시도
                    sleep 2
                    if aws ec2 delete-security-group --group-id "$sg" --region "$AWS_REGION" 2>/dev/null; then
                        echo "    ✅ 규칙 정리 후 삭제 성공"
                    else
                        echo "    ❌ 삭제 실패 (다른 리소스가 사용 중일 수 있음)"
                    fi
                fi
            done
        else
            echo "  ✅ Kubernetes 보안 그룹 없음"
        fi
        echo ""
        
        # 3. Load Balancer 확인
        echo "⚖️  Load Balancer 확인..."
        ALB_ARNS=$(aws elbv2 describe-load-balancers \
            --region "$AWS_REGION" \
            --query "LoadBalancers[?VpcId==\`$VPC_ID\`].LoadBalancerArn" \
            --output text 2>/dev/null || echo "")
        
        if [ -n "$ALB_ARNS" ]; then
            echo "⚠️  남은 Load Balancer 발견 (Kubernetes Ingress):"
            for alb_arn in $ALB_ARNS; do
                echo "  - 삭제: $alb_arn"
                # Load Balancer는 삭제되면 자동으로 보안 그룹도 삭제됨
                aws elbv2 delete-load-balancer --load-balancer-arn "$alb_arn" --region "$AWS_REGION" 2>/dev/null || true
            done
            echo "  ⏳ Load Balancer 삭제 대기 (10초)..."
            sleep 10
        else
            echo "  ✅ Load Balancer 없음"
        fi
        echo ""
        
        # 4. ENI (Elastic Network Interface) 확인
        echo "🌐 ENI 확인..."
        ENI_IDS=$(aws ec2 describe-network-interfaces \
            --filters "Name=vpc-id,Values=$VPC_ID" \
            --region "$AWS_REGION" \
            --query 'NetworkInterfaces[?Status==`available`].NetworkInterfaceId' \
            --output text 2>/dev/null || echo "")
        
        if [ -n "$ENI_IDS" ]; then
            echo "⚠️  남은 ENI 발견:"
            for eni in $ENI_IDS; do
                echo "  - 삭제: $eni"
                aws ec2 delete-network-interface --network-interface-id "$eni" --region "$AWS_REGION" 2>/dev/null || true
            done
        else
            echo "  ✅ 남은 ENI 없음"
        fi
        echo ""
    else
        echo "ℹ️  VPC ID를 가져올 수 없습니다 (이미 삭제되었거나 State 파일 없음)"
        echo ""
    fi
    
    echo "⏳ AWS 리소스 정리 완료 대기 (60초)..."
    echo "   (AWS API 비동기 처리 완료 대기)"
    sleep 60
    echo ""
else
    echo "ℹ️  Terraform State 파일이 없습니다 (새 배포 또는 이미 삭제됨)"
    echo ""
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣ Terraform 인프라 삭제"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Terraform 리소스 확인
if terraform state list >/dev/null 2>&1; then
    RESOURCE_COUNT=$(terraform state list 2>/dev/null | wc -l | tr -d ' ')
    echo "📊 현재 Terraform 리소스 개수: $RESOURCE_COUNT"
    echo ""
    
    if [ "$RESOURCE_COUNT" -gt 0 ]; then
        echo "🗑️  Terraform destroy 실행..."
        terraform destroy -auto-approve
        
        if [ $? -eq 0 ]; then
            echo ""
            echo "✅ Terraform 인프라 삭제 완료!"
        else
            echo ""
            echo "❌ Terraform destroy 실패!"
            echo ""
            echo "💡 남은 리소스 확인:"
            echo "   aws ec2 describe-volumes --region $AWS_REGION"
            echo "   aws ec2 describe-security-groups --filters Name=vpc-id,Values=$VPC_ID --region $AWS_REGION"
            exit 1
        fi
    else
        echo "ℹ️  삭제할 Terraform 리소스가 없습니다."
    fi
else
    echo "ℹ️  Terraform State 파일이 없습니다."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 완전 삭제 완료!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "💰 비용 절감:"
echo "   - EC2 인스턴스: $0/월"
echo "   - EBS 볼륨: $0/월"
echo "   - Load Balancer: $0/월"
echo ""
echo "📝 다시 생성하려면:"
echo "   ./scripts/provision.sh"
echo ""

