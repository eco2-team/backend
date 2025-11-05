## 📋 변경 사항 요약

### 주요 수정 사항
- [ ] Prometheus CPU 요청 최적화 (1000m → 500m)
- [ ] ArgoCD 502 Bad Gateway 해결 (프로토콜 불일치 수정)
- [ ] ALB Provider ID 자동 설정 로직 추가
- [ ] Route53 A 레코드 관리 Terraform → Ansible 이관
- [ ] VPC 삭제 지연 문제 해결
- [ ] 모니터링 노드 인스턴스 타입 업그레이드

---

## 🔧 Infrastructure 변경 사항

### Ansible Playbooks
- **08-monitoring.yml**: Prometheus CPU 요청 500m으로 최적화
- **03-1-set-provider-id.yml** (신규): Worker 노드 Provider ID 자동 설정
- **03-worker-join.yml**: Provider ID 설정 로직 추가 (Ansible Handler 오류 수정)
- **07-ingress-resources.yml**: ArgoCD backend-protocol HTTP로 수정, Service Port 80으로 변경
- **site.yml**: 
  - Worker join 대상 그룹 수정 (workers,storage → workers,rabbitmq,postgresql,redis,monitoring)
  - Route53 업데이트 실행 위치 수정 (master → localhost)
  - Provider ID 설정 task 추가

### Terraform
- **alb-controller-iam.tf**: 
  - `elasticloadbalancing:AddTags` 권한 제약 조건 제거
  - `elasticloadbalancing:DescribeListenerAttributes` 권한 추가
- **route53.tf**: 모든 A 레코드 주석 처리 (Ansible에서 관리)
- **main.tf**: 모니터링 노드 t3.medium → t3.large 업그레이드

### Scripts
- **destroy-with-cleanup.sh**: 
  - ALB 삭제 완전 대기 로직 추가
  - Security Group 삭제 재시도 로직 추가
  - NAT Gateway, VPC Endpoints, VPC Peering Connections 삭제 로직 추가
  - EBS 볼륨 최종 확인 및 삭제 로직 추가
- **configure-subpath.sh** (신규): ArgoCD/Grafana 서브 경로 설정 자동화
- **update-route53-to-alb.sh** (신규): Route53 A 레코드 ALB 연결 수동 스크립트

---

## 📚 문서 추가

### 트러블슈팅 문서
1. **PROMETHEUS_PENDING.md**: CPU 부족으로 인한 Pending 문제 해결
   - 원인: k8s-monitoring 노드 CPU 부족 (2130m > 2000m)
   - 해결: Prometheus CPU 요청 500m으로 조정
   - 결과: 여유 CPU 370m (18%) 확보

2. **ARGOCD_502_BAD_GATEWAY.md**: ArgoCD 502 에러 해결
   - 원인: ALB가 HTTPS로 연결 시도, ArgoCD는 HTTP만 지원
   - 해결: Ingress backend-protocol을 HTTP로 변경, Service Port 80으로 변경
   - 결과: Target Health healthy, 정상 접속 가능

3. **ALB_PROVIDER_ID.md**: Worker 노드 Target 등록 실패 해결
   - 원인: Worker 노드의 providerID 형식 오류 (Instance ID 누락)
   - 해결: AWS CLI를 사용한 자동 설정 로직 추가
   - 결과: ALB가 Worker 노드를 Target Group에 자동 등록

4. **VPC_DELETION_DELAY.md**: VPC 삭제 지연 및 SG 삭제 실패 해결
   - 원인: Kubernetes ALB Controller가 생성한 AWS 리소스 미정리
   - 해결: destroy-with-cleanup.sh 대폭 개선
   - 결과: 전체 삭제 시간 50% 단축 (7-10분 → 3-5분)

5. **MANUAL_OPERATIONS_TO_IAC.md**: 수동 작업 자동화 문서
   - Route53 DNS 변경 (Master IP → ALB Alias)
   - Service 타입 변경 (ClusterIP → NodePort)
   - IAM 권한 추가
   - Provider ID 설정

6. **troubleshooting/README.md**: 전체 트러블슈팅 가이드
   - 7개 문제 카탈로그
   - 우선순위 표
   - 일반적인 디버깅 절차
   - 유용한 스크립트 안내

---

## 🧪 테스트 결과

### 검증 완료 항목
- [x] Prometheus Pod Running 상태 확인
- [x] k8s-monitoring 노드 CPU 할당률 81% (여유 19%)
- [x] ArgoCD 접속 테스트 (https://growbin.app/argocd)
- [x] Grafana 접속 테스트 (https://growbin.app/grafana)
- [x] ALB Target Health 모두 Healthy 확인
- [x] Route53 A 레코드 ALB Alias 확인
- [x] Worker 노드 Provider ID 형식 확인
- [x] VPC 삭제 시간 3-5분 이내 확인

### 클러스터 상태
```
kubectl get nodes
NAME              STATUS   ROLES           AGE   VERSION
k8s-master        Ready    control-plane   18h   v1.28.3
k8s-worker-1      Ready    <none>          18h   v1.28.3
k8s-worker-2      Ready    <none>          18h   v1.28.3
k8s-rabbitmq      Ready    <none>          18h   v1.28.3
k8s-postgresql    Ready    <none>          18h   v1.28.3
k8s-redis         Ready    <none>          18h   v1.28.3
k8s-monitoring    Ready    <none>          18h   v1.28.3
```

```
kubectl get pods -n monitoring
NAME                                                      READY   STATUS    RESTARTS   AGE
alertmanager-prometheus-kube-prometheus-alertmanager-0    2/2     Running   0          18h
prometheus-grafana-bf57b9dfb-4lppm                        3/3     Running   0          17h
prometheus-kube-prometheus-operator-6888548dbc-4gsjj      1/1     Running   0          18h
prometheus-prometheus-kube-prometheus-prometheus-0        2/2     Running   0          30m  ✅
```

---

## 📊 리소스 변경 사항

### k8s-monitoring 노드 (t3.large, 2 vCPU)

#### Before
```
현재 사용: 1130m (56%)
Prometheus 요청: 1000m
필요 총량: 2130m > 2000m ❌ (Pending)
```

#### After
```
현재 사용: 1130m (56%)
Prometheus 요청: 500m
필요 총량: 1630m (81%) ✅ (Running)
여유 CPU: 370m (18%)
```

---

## 🔍 Breaking Changes

**없음** - 모든 변경 사항은 기존 기능 유지 또는 개선

---

## 📝 Migration Guide

### 기존 클러스터에 적용 시

1. **Prometheus CPU 조정**
```bash
kubectl patch prometheus prometheus-kube-prometheus-prometheus -n monitoring --type merge -p '{
  "spec": {
    "resources": {
      "requests": {
        "cpu": "500m",
        "memory": "2Gi"
      }
    }
  }
}'
```

2. **ArgoCD Ingress 수정**
```bash
kubectl annotate ingress argocd-ingress -n argocd \
  alb.ingress.kubernetes.io/backend-protocol=HTTP --overwrite

kubectl patch ingress argocd-ingress -n argocd --type json -p '[
  {
    "op": "replace",
    "path": "/spec/rules/0/http/paths/0/backend/service/port/number",
    "value": 80
  }
]'
```

3. **Provider ID 설정** (Master 노드에서)
```bash
cd /home/ubuntu/backend/ansible
ansible-playbook playbooks/03-1-set-provider-id.yml
```

### 신규 클러스터 구축 시
```bash
./scripts/cluster/build-cluster.sh
```
→ 모든 수정 사항이 자동 적용됩니다.

---

## 🔗 관련 이슈

- Prometheus Pod Pending 문제
- ArgoCD 502 Bad Gateway 문제
- ALB Target 등록 실패 문제
- VPC 삭제 지연 문제

---

## ✅ Checklist

- [x] 코드 변경 사항 테스트 완료
- [x] 트러블슈팅 문서 작성
- [x] 클러스터 정상 작동 확인
- [x] 리소스 할당 최적화 확인
- [x] 네트워크 라우팅 정상 확인
- [x] 모든 서비스 접속 가능 확인

---

## 📸 스크린샷

### Prometheus 정상 작동
```
kubectl get pods -n monitoring | grep prometheus
prometheus-prometheus-kube-prometheus-prometheus-0   2/2   Running   0   30m
```

### ALB Target Health
```
aws elbv2 describe-target-health --target-group-arn <TG_ARN>
→ All targets: healthy
```

### 접속 URL
- ✅ https://growbin.app/grafana
- ✅ https://growbin.app/argocd

---

## 💡 추가 개선 사항

### 향후 고려사항
1. Prometheus 메트릭 증가 시 CPU 요청 조정 필요 (500m → 750m)
2. 모니터링 노드 t3.large → t3.xlarge 업그레이드 고려 (추가 확장 시)
3. Grafana를 별도 Worker 노드로 분리 검토 (노드 분산)

---

## 🙏 리뷰어를 위한 노트

### 중점 확인 사항
1. **Ansible Playbook 변경**: Worker join 대상 그룹 수정이 올바른지 확인
2. **Terraform IAM 권한**: AddTags 제약 조건 제거가 보안상 문제없는지 확인
3. **Route53 관리 이관**: Terraform → Ansible 이관이 적절한지 확인
4. **Provider ID 로직**: AWS CLI 기반 자동 설정이 모든 환경에서 작동하는지 확인

### 테스트 환경
- AWS Region: ap-northeast-2 (Seoul)
- Kubernetes: v1.28.3
- Terraform: v1.5.7
- Ansible: v2.15.5

---

**담당자**: @mango  
**작업 기간**: 2025-11-04  
**영향받는 컴포넌트**: Prometheus, ArgoCD, ALB, Route53, Worker Nodes

