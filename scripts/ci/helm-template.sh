#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTPUT_DIR="${ROOT_DIR}/ci-artifacts/helm"

mkdir -p "${OUTPUT_DIR}"

charts=(
  "alb-controller;aws-load-balancer-controller;https://aws.github.io/eks-charts;1.7.1;platform/helm/alb-controller"
  "external-dns;external-dns;https://kubernetes-sigs.github.io/external-dns/;1.15.2;platform/helm/external-dns"
  "calico;tigera-operator;https://docs.tigera.io/calico/charts;v3.27.0;platform/helm/calico"
  "kube-prometheus-stack;kube-prometheus-stack;https://prometheus-community.github.io/helm-charts;56.21.1;platform/helm/kube-prometheus-stack"
  "grafana;grafana;https://grafana.github.io/helm-charts;8.5.9;platform/helm/grafana"
)

for chart_entry in "${charts[@]}"; do
  IFS=';' read -r NAME CHART REPO VERSION BASE_DIR <<<"${chart_entry}"
  for ENV in dev prod; do
    PATCH_FILE="${ROOT_DIR}/${BASE_DIR}/${ENV}/patch-application.yaml"
    SOURCE_FILE="${PATCH_FILE}"

    if [[ ! -f "${SOURCE_FILE}" ]]; then
      APP_FILE="$(
python3 - "${ROOT_DIR}" "${ENV}" "${REPO}" "${CHART}" <<'PY'
import pathlib
import sys

import yaml

root = pathlib.Path(sys.argv[1])
env = sys.argv[2]
repo = sys.argv[3]
chart = sys.argv[4]
apps_dir = root / "clusters" / env / "apps"
if not apps_dir.is_dir():
    sys.exit(0)
matches = []
for path in sorted(apps_dir.glob("*.yaml")):
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError:
        continue
    spec = data.get("spec") or {}
    source = spec.get("source") or {}
    repo_url = str(source.get("repoURL") or "").strip()
    chart_name = str(source.get("chart") or "").strip()
    if repo_url == repo and chart_name == chart:
        matches.append(path.as_posix())
if matches:
    print(matches[0])
PY
      )"
      if [[ -n "${APP_FILE}" ]]; then
        echo "ℹ️  Using Application manifest ${APP_FILE} for ${NAME} (${ENV})" >&2
        SOURCE_FILE="${APP_FILE}"
      else
      echo "⚠️  Skipping ${NAME} (${ENV}) – patch file not found: ${PATCH_FILE}" >&2
      continue
    fi
    fi

    VALUES_CONTENT="$(
python3 - "${SOURCE_FILE}" <<'PY'
import pathlib
import sys

import yaml

path = pathlib.Path(sys.argv[1])
data = yaml.safe_load(path.read_text()) or {}
spec = data.get("spec") or {}
source = spec.get("source") or {}
helm = source.get("helm") or {}
values = helm.get("valuesObject") if helm else None
if values is None:
    yaml.safe_dump({}, sys.stdout, sort_keys=False)
else:
    yaml.safe_dump(values, sys.stdout, sort_keys=False)
PY
)"
    TMP_VALUES="$(mktemp)"
    printf "%s" "${VALUES_CONTENT}" > "${TMP_VALUES}"
    OUTPUT_FILE="${OUTPUT_DIR}/${NAME}-${ENV}.yaml"
    echo "::group::helm template ${NAME} (${ENV})"
    helm template "${ENV}-${NAME}" "${CHART}" \
      --repo "${REPO}" \
      --version "${VERSION}" \
      --namespace "ci-${NAME}-${ENV}" \
      -f "${TMP_VALUES}" \
      > "${OUTPUT_FILE}"
    echo "Rendered manifest saved to ${OUTPUT_FILE}"
    echo "::endgroup::"
    rm -f "${TMP_VALUES}"
  done
done

ls -1 "${OUTPUT_DIR}"
