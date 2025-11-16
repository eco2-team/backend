# External Secrets Operator CRDs

- Source: https://github.com/external-secrets/external-secrets (tag v0.9.11)
- Bundle: `deploy/crds/bundle.yaml` (모든 `externalsecrets.io` CRD 포함)

Wave 10에서 ESO Helm Chart를 설치하기 전에 `kubectl apply -k platform/crds/external-secrets`로 CRD를 먼저 등록한다.
