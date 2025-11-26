#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTPUT_DIR="${ROOT_DIR}/ci-artifacts/kustomize"
mkdir -p "${OUTPUT_DIR}"

TARGETS=(
  "workloads/namespaces/dev"
  "workloads/namespaces/prod"
  "workloads/network-policies/dev"
  "workloads/network-policies/prod"
  "workloads/rbac-storage/dev"
  "workloads/rbac-storage/prod"
  "workloads/secrets/external-secrets/dev"
  "workloads/secrets/external-secrets/prod"
  "platform/cr/dev"
  "platform/cr/prod"
  "workloads/ingress/apps/dev"
  "workloads/ingress/apps/prod"
)

files=()
for target in "${TARGETS[@]}"; do
  KUSTOMIZATION="${ROOT_DIR}/${target}/kustomization.yaml"
  if [[ ! -f "${KUSTOMIZATION}" ]]; then
    echo "⚠️  Skipping ${target} – kustomization.yaml not found" >&2
    continue
  fi
  SAFE_NAME="$(echo "${target}" | tr '/.' '-')"
  OUTPUT_FILE="${OUTPUT_DIR}/${SAFE_NAME}.yaml"
  echo "::group::kustomize build ${target}"
  kustomize build "${ROOT_DIR}/${target}" > "${OUTPUT_FILE}"
  files+=("${OUTPUT_FILE}")
  echo "Rendered ${target} -> ${OUTPUT_FILE}"
  echo "::endgroup::"
done

if [[ ${#files[@]} -eq 0 ]]; then
  echo "❌ No Kustomize outputs were generated" >&2
  exit 1
fi

KUBECONFORM_BIN="${KUBECONFORM_BIN:-kubeconform}"
if ! command -v "${KUBECONFORM_BIN}" >/dev/null 2>&1; then
  echo "❌ kubeconform binary not found (KUBECONFORM_BIN=${KUBECONFORM_BIN})" >&2
  exit 1
fi

echo "::group::kubeconform validation"
"${KUBECONFORM_BIN}" \
  -strict \
  -ignore-missing-schemas \
  -schema-location default \
  -schema-location "https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json" \
  "${files[@]}"
echo "::endgroup::"

ls -1 "${OUTPUT_DIR}"
