# ALB Controller CRDs

- Source: https://github.com/kubernetes-sigs/aws-load-balancer-controller (tag v2.7.1)
- Manifest: `docs/install/crds.yaml`
- Applies `TargetGroupBinding` (`elbv2.k8s.aws/v1beta1`) and related resources.

`kubectl apply -k platform/crds/alb-controller` 로 Wave -1 단계에서 먼저 적용한다.
