#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MANIFEST="${1:-${ROOT_DIR}/ci-artifacts/render/combined.yaml}"

if [[ ! -f "${MANIFEST}" ]]; then
  echo "❌ Combined manifest not found: ${MANIFEST}" >&2
  exit 1
fi

echo "::group::Apply CRDs"
CRD_ROOT="${ROOT_DIR}/platform/crds"
if [[ -d "${CRD_ROOT}/dev" || -d "${CRD_ROOT}/prod" ]]; then
  for ENV in dev prod; do
    CRD_PATH="${CRD_ROOT}/${ENV}"
    if [[ -d "${CRD_PATH}" ]]; then
      echo "Applying CRDs for ${ENV}: ${CRD_PATH}"
      kubectl apply -k "${CRD_PATH}"
    fi
  done
else
  kubectl apply -k "${CRD_ROOT}"
fi
echo "::endgroup::"

echo "::group::Server-side dry-run"
kubectl apply --server-side --dry-run=server -f "${MANIFEST}"
echo "::endgroup::"
