#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HELM_DIR="${ROOT_DIR}/ci-artifacts/helm"
KUSTOMIZE_DIR="${ROOT_DIR}/ci-artifacts/kustomize"
OUTPUT_DIR="${ROOT_DIR}/ci-artifacts/render"

mkdir -p "${OUTPUT_DIR}"

if [[ ! -d "${HELM_DIR}" ]]; then
  echo "❌ Helm manifest directory not found: ${HELM_DIR}" >&2
  exit 1
fi

if [[ ! -d "${KUSTOMIZE_DIR}" ]]; then
  echo "❌ Kustomize manifest directory not found: ${KUSTOMIZE_DIR}" >&2
  exit 1
fi

cat "${HELM_DIR}"/*.yaml > "${OUTPUT_DIR}/helm.yaml"
cat "${KUSTOMIZE_DIR}"/*.yaml > "${OUTPUT_DIR}/kustomize.yaml"
cat "${OUTPUT_DIR}/helm.yaml" "${OUTPUT_DIR}/kustomize.yaml" > "${OUTPUT_DIR}/combined.yaml"

echo "Helm manifests:    ${OUTPUT_DIR}/helm.yaml"
echo "Kustomize manifests: ${OUTPUT_DIR}/kustomize.yaml"
echo "Combined manifest: ${OUTPUT_DIR}/combined.yaml"

ls -1 "${OUTPUT_DIR}"
