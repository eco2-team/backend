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
├─ helm/
│   ├─ <component>/
│   │   ├─ base/
│   │   │   ├─ application.yaml
│   │   │   └─ kustomization.yaml
│   │   ├─ dev/
│   │   │   ├─ kustomization.yaml
│   │   │   └─ patch-application.yaml
│   │   └─ prod/
│   │       ├─ kustomization.yaml
│   │       └─ patch-application.yaml
│   └─ ...
├─ crds/
│   └─ <component>/{base,dev,prod}/kustomization.yaml

workloads/
└─ platform/
    └─ (필요 시 helm/crd 공통 스펙을 재사용하기 위한 base/overlay)
```

### 설계 원칙
1. **CRD 선행**: Helm chart 설치 전 CRD를 명시적으로 관리하면 upgrade 시 충돌을 방지할 수 있다(CNCF 권장).  
2. **환경별 Application**: ApplicationSet 대신, dev/prod 각각을 독립 `Application`으로 정의해 소유권을 명확히 한다(파일 위치: `platform/helm/<component>/{base,dev,prod}`).  
3. **Base + Overlay**: 공통 스펙은 `platform/helm/<component>/base`에, 환경별 차이점은 `dev`/`prod`에 정의한다. 대부분의 경우 Kustomize overlay가 중복을 줄이고 유지보수가 쉽지만, 매우 단순한 차트면 복사본으로 운영하는 것도 가능하다.  
4. **연속 배포**: `ARGOCD_SYNC_WAVE_PLAN.md`에 따라 Operators(25 Wave) → Instances(35 Wave) 순서를 유지한다.  
5. **Values-less 원칙**: Helm 설정은 가능하면 env별 Application YAML 안의 `helm.parameters` 또는 `helm.valuesObject`로 직접 정의한다(별도 values 파일 미사용).

### 1.1 Helm(플랫폼)과 Kustomize(업무 워크로드)를 분리하는 이유

- **역할/책임 구분**: Helm이 담당하는 컴포넌트는 대부분 클러스터 범위 인프라(ALB Controller, Operators 등)이고, Kustomize는 도메인 서비스/워크로드에 집중한다. 디렉터리·파이프라인을 분리하면 담당 팀과 리뷰 라인이 자연스럽게 나뉘고 Git 히스토리도 책임 영역별로 남는다.
- **배포 수명주기 차이**: 플랫폼 계층은 버전 업·보안 패치 등 인프라 주기로 움직이고, 워크로드는 기능 릴리스 주기를 따른다. 한 Kustomize 트리 안에 혼합하면 Sync Wave나 승인 플로우가 얽히므로, `platform/helm/<component>/<env>`처럼 별도 루트 앱을 둬 독립적으로 배포/롤백할 수 있게 한다.
- **충돌/검증 최소화**: Helm 린트·렌더링과 Kustomize 빌드는 도구·검증 포인트가 다르다. 물리적으로 분리하면 CI 파이프라인도 단순해지고, 한쪽 변경이 다른 쪽 검증에 영향을 주는 일이 줄어든다.

---

## 2. Helm + ArgoCD 패턴

파트별 공통 `platform/helm/<component>/base/application.yaml` 템플릿:

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
    repoURL: https://aws.github.io/eks-charts
    chart: aws-load-balancer-controller
    targetRevision: 1.7.1
    helm:
      releaseName: aws-load-balancer-controller
      valuesObject:
        serviceAccount:
          create: false
          name: aws-load-balancer-controller
  destination:
    server: https://kubernetes.default.svc
    namespace: kube-system
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

> **중요**: 더 이상 ApplicationSet을 사용하지 않는다. dev용 Application은 dev 프로젝트/브랜치(`refactor/gitops-sync-wave`), prod용 Application은 prod 프로젝트/브랜치(`main`)만 바라보게 구성한다. 공통 스펙을 재사용해야 하면 `workloads/platform/<component>/base` 디렉터리에 템플릿을 두고, env 디렉터리에서 Kustomize `patches`나 `configurations`로 확장한다.

### 2.1 클러스터 루트와 연계

- `clusters/dev/apps/15-alb-controller.yaml` 처럼 루트 App은 `path: platform/helm/alb-controller/dev`를 직접 참조한다.
- Prod 루트 앱은 동일 Wave에서 `path: platform/helm/alb-controller/prod`를 참조한다.
- 공통 스펙을 재사용하는 경우, `platform/helm/alb-controller/base`를 Kustomize로 묶어 env 디렉터리가 `resources: ["../base"]` 형태로 참조하게 할 수 있다.

### 2.2 Helm Base/Overlay 패턴 적용 가능 여부

- Argo Application은 일반 YAML이므로 Kustomize를 이용해 `platform/helm/<component>/base/kustomization.yaml`을 만들고, `dev`·`prod` 디렉터리가 `resources: ["../base"]` 형태로 참조할 수 있다.
- Base에서는 공통 `spec.source`와 Sync 옵션만 정의하고, env 디렉터리에서는 `patchesStrategicMerge`로 `project`, `helm.parameters`, `destination.namespace` 등을 덮어쓰는 방식이 가능하다.
- Helmfile, Cue, ytt 등 템플릿 도구를 사용해 동일한 구조를 생성할 수도 있으나, 현재 리포지토리 패턴과 가장 잘 맞는 것은 Kustomize overlay 패턴이다.

---

## 3. 컴포넌트별 가이드

### 3.1 ALB Controller (AWS Load Balancer Controller)
- **CRD**: `TargetGroupBinding` 등 CRD를 `platform/crds/alb-controller`에서 관리.  
- **Helm Source**: AWS GitHub/EKS Charts `https://aws.github.io/eks-charts`, chart `aws-load-balancer-controller`, 버전 `1.8.3`.  
- **Manifest 위치**:  
  - dev: `platform/helm/alb-controller/dev`  
  - prod: `platform/helm/alb-controller/prod`  
- **필수 설정**: IRSA Role (`AWSLoadBalancerControllerIAMPolicy`), `clusterName`, `region`, `vpcId`, `publicSubnetIds`, `albSecurityGroupId` 등을 `helm.parameters`로 지정하되, 민감 값은 `valueFrom.secretKeyRef`로 주입한다.  
- **Base 재사용**: 반복되는 spec이 많다면 `workloads/platform/alb-controller/base`에 공통 manifest를 두고 env별 Kustomize Overlay를 통해 `Application` YAML을 생성할 수 있다.

- **Manifest 위치**: `platform/helm/kube-prometheus-stack/{dev,prod}`
- Prometheus Operator + 기본 인스턴스 번들을 하나의 Helm chart로 관리하되, Instance CR/CRD는 `platform/cr/{base,dev,prod}` Kustomize 경로에서 계속 관리한다.
- Retention, Alertmanager receiver 등은 `helm.valuesObject`나 parameters로 직접 정의한다.
- Sync Wave 20(Operator) → Wave 30(Instance) 전략을 준수한다.

- **Manifest 위치**: `platform/helm/postgres-operator/{dev,prod}`
- S3 backup bucket, TLS secret 등 Prod 설정은 `helm.parameters`/`valuesObject`에서 환경별로 지정한다.
- 데이터 인스턴스는 Kustomize `platform/cr/{dev,prod}` overlay에서 관리한다.

- **Manifest 위치**: `platform/helm/redis-operator/{dev,prod}`
- Operator만 Helm으로 설치하고, 실제 Redis CR은 `platform/cr/{base,dev,prod}` 디렉터리에서 정의한다.

- **Manifest 위치**: `platform/helm/external-secrets/{dev,prod}`
- AWS Secrets Manager/SSM Parameter Store 연동을 위한 Controller.
- 환경별 `ClusterSecretStore` 이름, IAM Role ARN을 `helm.parameters` 또는 `valuesObject`로 주입한다.
- Sync Wave 20에 배치해 Secrets → Apps 순서를 지킨다.

### 3.6 Atlantis
- Terraform plan/apply 자동화를 위한 Helm chart.  
- GitHub webhook secret, Terraform repos, allowlist를 env별 Application YAML의 `helm.parameters`로 정의한다.

---

## 4. 운영 팁

1. **CRD 버전 관리**: `platform/crds` 폴더에는 chart에서 제공하는 `crds/` 내용을 복사하고, 버전 업 시 diff를 검토.  
2. **렌더링 검증**: `helm template <chart> --version <x> --set-file ...` 혹은 `--set` 플래그로 Application YAML에서 정의한 parameters를 동일하게 전달해 사전 렌더링한다.  
3. **ArgoCD Notifications**: 플랫폼 App은 Slack/PagerDuty 알림을 활성화해 Operator 장애를 즉시 파악.  
4. **보안**: 민감 값(VPC ID, IAM Role 등)은 `helm.parameters.valueFrom.secretKeyRef` 또는 External Secret 참조로 주입한다.  
5. **자동화**: `platform/helm` 하위 차트에 대해 CI로 `helm lint`를 수행해 Chart upgrade 시 오류를 방지.

---

> 이 가이드는 벤더 스택(Helm 중심) 구성에 대한 기준이며, 새로운 Operator/Controller 도입 시 `platform/crds`와 `platform/helm` 폴더를 동일 패턴으로 확장한다.

