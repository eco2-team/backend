#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTPUT_DIR="${ROOT_DIR}/ci-artifacts/helm"

mkdir -p "${OUTPUT_DIR}"

charts=(
  "alb-controller;aws-load-balancer-controller;https://aws.github.io/eks-charts;1.7.1;platform/helm/alb-controller/values"
  "external-dns;external-dns;https://kubernetes-sigs.github.io/external-dns/;1.15.2;platform/helm/external-dns/values"
  "calico;tigera-operator;https://docs.tigera.io/calico/charts;v3.27.0;platform/helm/calico/values"
  "kube-prometheus-stack;kube-prometheus-stack;https://prometheus-community.github.io/helm-charts;56.21.1;platform/helm/kube-prometheus-stack/values"
  "grafana;grafana;https://grafana.github.io/helm-charts;8.5.9;platform/helm/grafana/values"
)

for chart_entry in "${charts[@]}"; do
  IFS=';' read -r NAME CHART REPO VERSION VALUES_DIR <<<"${chart_entry}"
  for ENV in dev prod; do
    VALUES_FILE="${ROOT_DIR}/${VALUES_DIR}/${ENV}.yaml"
    if [[ ! -f "${VALUES_FILE}" ]]; then
      echo "⚠️  Skipping ${NAME} (${ENV}) – values file not found: ${VALUES_FILE}" >&2
      continue
    fi
    OUTPUT_FILE="${OUTPUT_DIR}/${NAME}-${ENV}.yaml"
    echo "::group::helm template ${NAME} (${ENV})"
    helm template "${ENV}-${NAME}" "${CHART}" \
      --repo "${REPO}" \
      --version "${VERSION}" \
      --namespace "ci-${NAME}-${ENV}" \
      -f "${VALUES_FILE}" \
      > "${OUTPUT_FILE}"
    echo "Rendered manifest saved to ${OUTPUT_FILE}"
    echo "::endgroup::"
  done
done

ls -1 "${OUTPUT_DIR}"

