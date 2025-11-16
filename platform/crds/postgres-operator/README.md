# Zalando Postgres Operator CRDs

- Source: https://github.com/zalando/postgres-operator (tag v1.10.0)
- CRD 목록:
  - `postgresqls.acid.zalan.do`
  - `operatorconfigurations.acid.zalan.do`

Helm Operator 배포 전에 `kubectl apply -k platform/crds/postgres-operator`로 Wave -1 단계에서 적용한다.
