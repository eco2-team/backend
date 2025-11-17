#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTPUT_DIR="${ROOT_DIR}/ci-artifacts/ct/charts"
rm -rf "${OUTPUT_DIR}"
mkdir -p "${OUTPUT_DIR}"

charts=(
  "alb-controller;aws-load-balancer-controller;https://aws.github.io/eks-charts;1.7.1;platform/helm/alb-controller/values"
  "external-dns;external-dns;https://kubernetes-sigs.github.io/external-dns/;1.15.2;platform/helm/external-dns/values"
  "calico;tigera-operator;https://docs.tigera.io/calico/charts;v3.27.0;platform/helm/calico/values"
  "kube-prometheus-stack;kube-prometheus-stack;https://prometheus-community.github.io/helm-charts;56.21.1;platform/helm/kube-prometheus-stack/values"
  "grafana;grafana;https://grafana.github.io/helm-charts;8.5.9;platform/helm/grafana/values"
)

for entry in "${charts[@]}"; do
  IFS=';' read -r NAME CHART REPO VERSION VALUES_DIR <<<"${entry}"
  for ENV in dev prod; do
    VALUES_FILE="${ROOT_DIR}/${VALUES_DIR}/${ENV}.yaml"
    if [[ ! -f "${VALUES_FILE}" ]]; then
      echo "⚠️  Skipping ${NAME} (${ENV}) – missing values file: ${VALUES_FILE}" >&2
      continue
    fi
    CHART_DIR="${OUTPUT_DIR}/${NAME}-${ENV}"
    mkdir -p "${CHART_DIR}"
    cat > "${CHART_DIR}/Chart.yaml" <<EOF
apiVersion: v2
name: ${NAME}-${ENV}
description: Stub chart for ${NAME} (${ENV}) chart-testing
type: application
version: 0.1.0
dependencies:
  - name: ${CHART}
    version: ${VERSION}
    repository: ${REPO}
EOF
    cp "${VALUES_FILE}" "${CHART_DIR}/values.yaml"
  done
done

echo "Generated stub charts:"
find "${OUTPUT_DIR}" -maxdepth 2 -name Chart.yaml -print

