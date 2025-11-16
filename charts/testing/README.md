# charts/testing

이 디렉터리는 GitHub Actions에서 `chart-testing (ct)`를 실행하기 위한 **Stub Chart** 모음을 보관합니다.  
실제 운영 Helm 차트(ALB Controller 등)는 AWS 리소스 의존성 때문에 Kind 환경에서 설치가 어려우므로, 값 구조를 검증할 수 있는 경량 차트를 별도로 유지합니다.

- `aws-load-balancer-controller-stub`  
  - AWS Load Balancer Controller 값 형태(clusterName, nodeSelector, tolerations 등)를 모의 Deployment로 검증  
  - `ct lint`/`ct install` 대상

`charts/ct.yaml` 은 chart-testing 설정 파일이며, `ci-quality-gate` 워크플로의 `helm-tests` 잡에서 사용됩니다.

