# Rebuild Scripts 13노드 업데이트

**브랜치**: `fix/rebuild-scripts-13nodes`  
**작성일**: 2025-11-06  
**목적**: 재구축 스크립트를 13노드 마이크로서비스 아키텍처에 맞게 업데이트

---

## 📋 변경 요약

### 수정된 스크립트

1. **`scripts/cluster/pre-rebuild-check.sh`**
   - 7노드 → 13노드 구성으로 전면 수정
   - Terraform 모듈 검증 (13개)
   - CNI Worker 수 업데이트 (12개)
   - 노드 레이블 검증 (12개)
   - 리소스 및 비용 정보 업데이트

2. **`scripts/maintenance/destroy-with-cleanup.sh`**
   - CloudFront Distribution 정리 추가
   - Route53 레코드 정리 (images.ecoeco.app, api.ecoeco.app)
   - ACM 인증서 정리 (ap-northeast-2, us-east-1)

3. **`scripts/cluster/auto-rebuild.sh`**
   - cleanup 스크립트 경로 수정 (`maintenance/destroy-with-cleanup.sh`)
   - 에러 핸들링 개선

---

## 🎯 주요 변경사항

### 1. pre-rebuild-check.sh - 13노드 구성 반영

#### Terraform 모듈 검증

```bash
# Before (7노드)
MODULES=("master" "worker_1" "worker_2" "rabbitmq" "postgresql" "redis" "monitoring")

# After (13노드)
MODULES=(
  "master"
  "api_waste" "api_auth" "api_userinfo" "api_location" "api_recycle_info" "api_chat_llm"
  "worker_storage" "worker_ai"
  "rabbitmq" "postgresql" "redis" "monitoring"
)
```

**검증 로직**:
- 총 13개 모듈 존재 확인
- 각 모듈이 `terraform/main.tf`에 정의되어 있는지 검증
- 모듈 수 불일치 시 에러

#### CNI Worker 수 업데이트

```bash
# Before
EXPECTED_WORKERS=6
EXPECTED_TOTAL_NODES=7

# After
EXPECTED_WORKERS=12  # 6 API + 2 Worker + 4 Infra (Master 제외)
EXPECTED_TOTAL_NODES=13
```

#### 노드 레이블 검증

```bash
# Before (7노드)
NODE_LABELS=("k8s-worker-1" "k8s-worker-2" "k8s-rabbitmq" "k8s-postgresql" "k8s-redis" "k8s-monitoring")

# After (13노드)
NODE_LABELS=(
  "k8s-api-waste" "k8s-api-auth" "k8s-api-userinfo" 
  "k8s-api-location" "k8s-api-recycle-info" "k8s-api-chat-llm"
  "k8s-worker-storage" "k8s-worker-ai"
  "k8s-rabbitmq" "k8s-postgresql" "k8s-redis" "k8s-monitoring"
)
```

**검증 방법**:
- `ansible/playbooks/label-nodes.yml` 파일 존재 확인
- 각 노드 이름이 플레이북에 정의되어 있는지 검증
- 12개 중 10개 이상 확인 시 통과

#### 예상 클러스터 구성 정보

```bash
총 13개 노드:
├─ Master (t3.large, 8GB)           - Control Plane
├─ API-Waste (t3.small, 2GB)        - 폐기물 분석 API
├─ API-Auth (t3.micro, 1GB)         - 인증/인가 API
├─ API-Userinfo (t3.micro, 1GB)     - 사용자 정보 API
├─ API-Location (t3.micro, 1GB)     - 지도/위치 API
├─ API-RecycleInfo (t3.micro, 1GB)  - 재활용 정보 API
├─ API-ChatLLM (t3.small, 2GB)      - LLM 채팅 API
├─ Worker-Storage (t3.medium, 4GB)  - Celery I/O Workers
├─ Worker-AI (t3.medium, 4GB)       - Celery Network Workers
├─ RabbitMQ (t3.small, 2GB)         - Message Queue
├─ PostgreSQL (t3.small, 2GB)       - Database
├─ Redis (t3.small, 2GB)            - Cache
└─ Monitoring (t3.large, 8GB)       - Prometheus + Grafana

총 vCPU: 18 cores
총 Memory: 26GB
총 Storage: 410GB
총 비용: ~$180/month
```

#### 네트워크 설정 정보

```bash
리전: ap-northeast-2 (Seoul)
가용 영역: 3개 (ap-northeast-2a, 2b, 2c)
VPC CIDR: 10.0.0.0/16
Public Subnets: 10.0.1.0/24, 10.0.2.0/24, 10.0.3.0/24
Pod CIDR: 192.168.0.0/16 (Calico VXLAN)
Service CIDR: 10.96.0.0/12

CNI: Calico (VXLAN Always, BGP Disabled)
Ingress: ALB Ingress Controller
DNS: Route53 (api.ecoeco.app)
CDN: CloudFront (images.ecoeco.app)
```

---

### 2. destroy-with-cleanup.sh - CDN 리소스 정리 추가

#### 🔧 EC2 인스턴스 명시적 종료 (NEW - Critical)

**문제**: Terraform destroy만으로는 EC2 인스턴스가 제대로 종료되지 않음

**해결**: EC2 인스턴스를 명시적으로 종료하는 로직 추가 (Step 0)

```bash
# 0. EC2 인스턴스 확인 및 종료
aws ec2 describe-instances \
  --filters "Name=vpc-id,Values=$VPC_ID" \
            "Name=instance-state-name,Values=running,stopped,stopping,pending"

# 인스턴스 종료
aws ec2 terminate-instances --instance-ids $EC2_IDS

# 종료 완료 대기 (최대 2분)
while [ $WAIT_COUNT -lt 60 ]; do
  # 2초마다 종료 상태 확인
  # terminated가 아닌 인스턴스 카운트
done
```

**특징**:
- VPC 내 모든 EC2 인스턴스 감지
- 인스턴스 정보 출력 (Name, ID, Type, State)
- 병렬 종료 (모든 인스턴스 동시 종료)
- 진행 상황 실시간 표시
- 타임아웃 보호 (최대 2분)

#### CloudFront Distribution 정리

```bash
# 4. CloudFront Distribution 확인 및 삭제
aws cloudfront list-distributions
→ Distribution 비활성화 (Enabled: false)
→ 배포 대기 (최대 3분)
→ Distribution 삭제
```

**처리 로직**:
1. 모든 CloudFront Distribution 조회
2. `Deployed` 상태인 Distribution 필터링
3. Distribution 비활성화 (Enabled = false)
4. 배포 완료 대기 (180초)
5. Distribution 삭제

**특징**:
- `jq`를 사용한 JSON 파싱
- ETag를 이용한 안전한 업데이트
- 상태 확인 후 삭제

#### Route53 레코드 정리

```bash
# 5. Route53 레코드 정리
aws route53 list-hosted-zones-by-name
→ Hosted Zone ID 조회 (ecoeco.app)
→ images.ecoeco.app 레코드 삭제
→ api.ecoeco.app 레코드 삭제
```

**정리 대상**:
- `images.ecoeco.app` (CloudFront CNAME or A Record)
- `api.ecoeco.app` (ALB A Record)

**처리 방법**:
1. Hosted Zone ID 조회
2. 각 레코드 ResourceRecordSet 조회
3. DELETE 액션으로 Change Batch 생성
4. Route53 API 호출

#### ACM 인증서 정리

```bash
# 6. ACM 인증서 정리 (ap-northeast-2 및 us-east-1)
# ap-northeast-2
aws acm list-certificates --region ap-northeast-2
→ InUseBy가 0인 인증서 삭제

# us-east-1 (CloudFront용)
aws acm list-certificates --region us-east-1
→ InUseBy가 0인 인증서 삭제
```

**특징**:
- **두 리전 모두 처리** (ap-northeast-2, us-east-1)
- CloudFront는 us-east-1 인증서만 사용하므로 별도 처리 필요
- 사용 중인 인증서는 건너뜀 (InUseBy > 0)

**삭제 조건**:
- `InUseBy` 카운트가 0
- `Status`가 `ISSUED`

---

### 3. auto-rebuild.sh - cleanup 경로 수정

#### 경로 수정

```bash
# Before
CLEANUP_SCRIPT="$SCRIPT_DIR/cleanup.sh"
if [ ! -f "$CLEANUP_SCRIPT" ]; then
    CLEANUP_SCRIPT="$SCRIPT_DIR/destroy-with-cleanup.sh"
fi

# After
CLEANUP_SCRIPT="$SCRIPT_DIR/../maintenance/destroy-with-cleanup.sh"

if [ ! -f "$CLEANUP_SCRIPT" ]; then
    echo "⚠️  cleanup script not found: $CLEANUP_SCRIPT"
    exit 1
fi
```

**변경 이유**:
- `scripts/` 디렉토리가 재구조화됨
- `destroy-with-cleanup.sh`가 `maintenance/` 디렉토리로 이동
- 명확한 경로 지정으로 에러 방지

#### 에러 핸들링 개선

```bash
if [ $CLEANUP_EXIT_CODE -ne 0 ]; then
    echo "⚠️  cleanup 실패 (exit code: $CLEANUP_EXIT_CODE)"
    echo "   일부 리소스가 남아있을 수 있습니다."
    echo "   계속 진행합니다..."
else
    echo "✅ Cleanup 완료!"
fi
```

**개선 사항**:
- 성공 시 메시지 추가
- 명확한 상태 피드백

---

## 🔧 주요 기술적 개선

### CloudFront 삭제 로직

**문제**: CloudFront Distribution은 즉시 삭제할 수 없음

**해결**:
1. Distribution을 먼저 비활성화 (Enabled = false)
2. 배포 완료 대기 (약 3분)
3. 배포 완료 후 삭제

**코드**:
```bash
# Get current config with ETag
CF_CONFIG=$(aws cloudfront get-distribution-config --id "$cf_id")
ETAG=$(echo "$CF_CONFIG" | jq -r '.ETag')

# Disable distribution
UPDATED_CONFIG=$(echo "$CF_CONFIG" | jq '.DistributionConfig.Enabled = false | .DistributionConfig')
aws cloudfront update-distribution \
    --id "$cf_id" \
    --distribution-config "$UPDATED_CONFIG" \
    --if-match "$ETAG"

# Wait for deployment
sleep 180

# Delete distribution
FINAL_ETAG=$(aws cloudfront get-distribution-config --id "$cf_id" --query 'ETag' --output text)
aws cloudfront delete-distribution --id "$cf_id" --if-match "$FINAL_ETAG"
```

### Route53 레코드 삭제

**문제**: Route53 레코드는 정확한 ResourceRecordSet이 필요

**해결**:
1. 전체 ResourceRecordSet 조회
2. JSON 형식 그대로 사용
3. Change Batch로 DELETE 액션 수행

**코드**:
```bash
# Get full record set
IMAGES_RECORD=$(aws route53 list-resource-record-sets \
    --hosted-zone-id "$HOSTED_ZONE_ID" \
    --query "ResourceRecordSets[?Name==\`images.ecoeco.app.\`] | [0]" \
    --output json)

# Create change batch
CHANGE_BATCH='{"Changes":[{"Action":"DELETE","ResourceRecordSet":'"$IMAGES_RECORD"'}]}'

# Apply change
aws route53 change-resource-record-sets \
    --hosted-zone-id "$HOSTED_ZONE_ID" \
    --change-batch "$CHANGE_BATCH"
```

### ACM 다중 리전 처리

**문제**: CloudFront는 us-east-1 리전 인증서만 사용

**해결**:
- ap-northeast-2 (ALB용)
- us-east-1 (CloudFront용)
- 두 리전 모두 별도로 처리

**코드**:
```bash
# ap-northeast-2
aws acm list-certificates --region ap-northeast-2

# us-east-1
aws acm list-certificates --region us-east-1
```

---

## 📊 테스트 체크리스트

### pre-rebuild-check.sh

- [ ] AWS 자격 증명 확인
- [ ] SSH 키 확인
- [ ] Terraform 설정 확인 (13개 모듈)
- [ ] Ansible 설정 확인 (CNI Worker 12개)
- [ ] 노드 레이블 확인 (12개 노드)
- [ ] 환경변수 확인
- [ ] 기존 리소스 충돌 확인

### destroy-with-cleanup.sh

- [ ] Kubernetes 리소스 정리
- [ ] EC2 인스턴스 종료 ⭐ NEW
- [ ] AWS 리소스 정리 (EBS, SG)
- [ ] ALB 삭제
- [ ] CloudFront Distribution 삭제
- [ ] Route53 레코드 삭제
- [ ] ACM 인증서 삭제 (ap-northeast-2)
- [ ] ACM 인증서 삭제 (us-east-1)
- [ ] ENI 정리
- [ ] Target Groups 삭제
- [ ] Terraform 리소스 삭제
- [ ] VPC 완전 삭제

### auto-rebuild.sh

- [ ] cleanup 스크립트 경로 확인
- [ ] cleanup 실행
- [ ] build-cluster.sh 실행
- [ ] 전체 프로세스 완료

---

## 🚀 사용 방법

### 1. Pre-Rebuild Check

```bash
cd /Users/mango/workspace/SeSACTHON/backend

# 재구축 전 환경 검증
./scripts/cluster/pre-rebuild-check.sh
```

**예상 출력**:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 Rebuild 전 체크리스트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【1】 AWS 자격 증명 확인
✅ AWS 자격 증명 환경변수 설정됨
✅ AWS 리전: ap-northeast-2 (Seoul) ✅

【2】 SSH 키 확인
✅ SSH 키 파일 존재 (~/.ssh/sesacthon.pem)
✅ SSH 키 권한 올바름 (400)

【3】 Terraform 설정 확인
✅ Terraform 리전: ap-northeast-2 ✅
✅ Terraform 모듈: master ✅
✅ Terraform 모듈: api_waste ✅
...
✅ 총 13개 모듈 확인 완료 ✅

【4】 Ansible 설정 확인
✅ CNI 플러그인: Calico ✅
✅ Pod CIDR: 192.168.0.0/16 ✅
✅ CNI 플레이북 Worker 수: 12 ✅
✅ CNI 플레이북 Total 노드 수: 13 ✅
✅ 노드 레이블 플레이북 존재 ✅
✅ 노드 레이블 설정 확인 (12/12개)

【최종 요약】
📊 예상 클러스터 구성 (13노드):
...
✅ Rebuild 준비 완료!
```

### 2. Destroy with Cleanup

```bash
# 기존 인프라 완전 삭제
./scripts/maintenance/destroy-with-cleanup.sh

# 또는 자동 모드
AUTO_MODE=true ./scripts/maintenance/destroy-with-cleanup.sh
```

**예상 소요 시간**:
- Kubernetes 리소스 정리: 2분
- **EC2 인스턴스 종료: 1-2분** ⭐ NEW
- ALB 삭제: 1-2분
- CloudFront 삭제: 3-5분
- Route53 레코드 삭제: 1분
- ACM 인증서 삭제: 1분
- Terraform 삭제: 5-10분
- **총 소요 시간: 약 15-25분** (기존 15-20분)

### 3. Auto Rebuild

```bash
# 완전 자동 재구축
./scripts/cluster/auto-rebuild.sh
```

**전체 프로세스**:
1. `destroy-with-cleanup.sh` 실행
2. `build-cluster.sh` 실행

**예상 소요 시간**:
- Cleanup: 15-20분
- Build: 20-30분
- **총 소요 시간: 약 35-50분**

---

## ⚠️ 주의사항

### CloudFront Distribution 삭제

- **시간 소요**: 비활성화 후 배포 완료까지 3-5분
- **대기 필요**: `sleep 180` 또는 상태 확인 루프
- **에러 처리**: 삭제 실패 시 수동 삭제 필요

### ACM 인증서

- **사용 중 인증서**: `InUseBy > 0`인 경우 삭제 불가
- **CloudFront 인증서**: us-east-1 리전에서 별도 처리
- **ALB 인증서**: ap-northeast-2 리전에서 처리

### Route53 레코드

- **Hosted Zone**: `ecoeco.app.` (점 필수!)
- **레코드 이름**: `images.ecoeco.app.`, `api.ecoeco.app.` (점 필수!)
- **삭제 실패**: ResourceRecordSet이 정확히 일치해야 함

### 네트워크 타임아웃

- **CloudFront**: 최대 5분 대기
- **ALB**: 최대 60초 대기
- **ENI**: 5초 대기 후 재시도

---

## 📝 문제 해결

### pre-rebuild-check.sh 실패

**문제**: Terraform 모듈 검증 실패
```
❌ Terraform 모듈 누락: api_waste
```

**해결**:
```bash
cd terraform
grep "module \"api_waste\"" main.tf

# 없으면 추가 필요
```

---

**문제**: CNI Worker 수 불일치
```
⚠️  ansible/playbooks/04-cni-install.yml의 EXPECTED_WORKERS 확인 필요 (예상: 12)
```

**해결**:
```bash
cd ansible/playbooks
vi 04-cni-install.yml

# 수정:
EXPECTED_WORKERS=12
EXPECTED_TOTAL_NODES=13
```

---

### destroy-with-cleanup.sh 실패

**문제**: CloudFront Distribution 삭제 실패
```
⚠️  Distribution 삭제 실패 (수동 삭제 필요)
```

**해결**:
```bash
# AWS Console에서 수동 삭제
# 1. CloudFront Distribution 비활성화
# 2. 배포 완료 대기
# 3. Distribution 삭제
```

---

**문제**: ACM 인증서 삭제 실패
```
⚠️  삭제 실패
ℹ️  사용 중이므로 건너뜀
```

**해결**:
```bash
# CloudFront나 ALB가 사용 중인지 확인
aws acm describe-certificate \
    --certificate-arn <ARN> \
    --region us-east-1 \
    --query 'Certificate.InUseBy'

# 사용 중인 리소스 삭제 후 재시도
```

---

## 🔗 참고 문서

- [INFRASTRUCTURE_REBUILD_GUIDE.md](../INFRASTRUCTURE_REBUILD_GUIDE.md)
- [CLUSTER_RESOURCES.md](infrastructure/CLUSTER_RESOURCES.md)
- [13NODES_COMPLETE_SUMMARY.md](../13NODES_COMPLETE_SUMMARY.md)
- [CDN_WARNINGS_AND_BEST_PRACTICES.md](CDN_WARNINGS_AND_BEST_PRACTICES.md)

---

**작성일**: 2025-11-06  
**브랜치**: fix/rebuild-scripts-13nodes  
**작성자**: AI Assistant


