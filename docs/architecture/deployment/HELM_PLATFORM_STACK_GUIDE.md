# Helm Platform Stack 구조 가이드

> **참고 레퍼런스**  
> - CNCF App Delivery WG: “Helm Best Practices” (CRD vs. Controller 설치 분리)  
> - Argo CD 공식 문서: Helm Application 배포 패턴  
> - AWS/EKS 블로그: aws-load-balancer-controller Helm 배포 가이드  
> - External Secrets Operator / Prometheus Operator 공식 Helm 차트 문서

---

## 1. 디렉토리 구조 (플랫폼 계층)

```
platform/
├─ crds/                # Wave -1에서 적용할 원본 CRD (선택)
│  ├─ alb-controller/
│  ├─ prometheus-operator/
│  ├─ postgres-operator/
│  └─ external-secrets/
└─ helm/                # 벤더 Helm Chart + ArgoCD Application
   ├─ alb-controller/
   │  ├─ app.yaml       # ArgoCD Application(Helm)
   │  └─ values/(dev|prod).yaml
   ├─ kube-prometheus-stack/
   ├─ postgres-operator/
   ├─ redis-operator/
   ├─ external-secrets-operator/
   └─ atlantis/
```

### 설계 원칙
1. **CRD 선행**: Helm chart 설치 전 CRD를 명시적으로 관리하면 upgrade 시 충돌을 방지할 수 있다(CNCF 권장).  
2. **환경별 values**: dev/prod를 별도 values 파일로 분리해 ArgoCD Application에서 `valueFiles`만 변경.  
3. **연속 배포**: `ARGOCD_SYNC_WAVE_PLAN.md`에 따라 Operators(25 Wave) → Instances(35 Wave) 순으로 Sync.

---

## 2. Helm + ArgoCD 패턴

파트별 공통 `app.yaml` 템플릿:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: alb-controller
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "15"
spec:
  project: platform
  source:
    repoURL: https://github.com/SeSACTHON/backend.git
    path: platform/helm/alb-controller
    helm:
      valueFiles:
        - values/prod.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: kube-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

> 환경에 따라 `values/dev.yaml`을 참조하도록 ApplicationSet 또는 Helm parameters를 활용한다.

---

## 3. 컴포넌트별 가이드

### 3.1 ALB Controller (AWS Load Balancer Controller)
- **CRD**: `TargetGroupBinding` 등 CRD를 `platform/crds/alb-controller`에서 관리.  
- **Helm Source**: AWS GitHub/EKS Charts `https://aws.github.io/eks-charts`, chart `aws-load-balancer-controller`, 버전 `1.8.3`(ArtifactHub 안정 릴리스).  
- **필수 설정**: IRSA Role (`AWSLoadBalancerControllerIAMPolicy`), `alb-controller-values` Secret에서 `clusterName`, `region`, `vpcId`, `publicSubnetIds`, `albSecurityGroupId` 주입.  
- **Values 예시**:  
  ```yaml
  clusterName: sesacthon-prod
  region: ap-northeast-2
  vpcId: {{ .Values.secrets.vpcId }}
  ```  
  (VPC ID는 `TERRAFORM_SECRET_INJECTION.md` 과정으로 Secret에서 주입)

### 3.2 kube-prometheus-stack
- Prometheus Operator + 기본 인스턴스 번들.  
- `values/prod.yaml`에서 Retention, Alertmanager receiver 등을 정의.  
- Sync Wave 20(Operator) → Wave 30(Instance) 전략을 준수.

### 3.3 Postgres Operator
- Percona PGO 또는 Crunchy Operator 중 선택.  
- Helm values에서 S3 backup bucket, TLS secret 등 Prod 설정을 분리.  
- 데이터 인스턴스는 Kustomize `workloads/data/postgres` overlay에서 관리.

### 3.4 Redis Operator
- Spotahome/Opstree/Redis Enterprise 중 정책에 맞는 차트를 선택.  
- Operator만 Helm으로 설치하고, 실제 RedisCluster CR은 Kustomize overlay에서 정의한다.

### 3.5 External Secrets Operator (ESO)
- AWS Secrets Manager/SSM Parameter Store 연동을 위한 Controller.  
- 환경별 `ClusterSecretStore` 이름, IAM Role ARN을 values에서 주입.  
- Sync Wave 20에 배치해 Secrets → Apps 순서를 지킨다.

### 3.6 Atlantis
- Terraform plan/apply 자동화를 위한 Helm chart.  
- values에 GitHub webhook secret, Terraform repos, allowlist를 환경별로 정의.

---

## 4. 운영 팁

1. **CRD 버전 관리**: `platform/crds` 폴더에는 chart에서 제공하는 `crds/` 내용을 복사하고, 버전 업 시 diff를 검토.  
2. **Values 검증**: `helm template -f values/prod.yaml .` 명령어로 사전 렌더링.  
3. **ArgoCD Notifications**: 플랫폼 App은 Slack/PagerDuty 알림을 활성화해 Operator 장애를 즉시 파악.  
4. **보안**: Sensible 값(VPC ID, IAM Role 등)은 `values/_base.yaml`에서 SecretKeyRef로 치환.  
5. **자동화**: `platform/helm` 하위 차트에 대해 CI로 `helm lint`를 수행해 Chart upgrade 시 오류를 방지.

---

> 이 가이드는 벤더 스택(Helm 중심) 구성에 대한 기준이며, 새로운 Operator/Controller 도입 시 `platform/crds`와 `platform/helm` 폴더를 동일 패턴으로 확장한다.

