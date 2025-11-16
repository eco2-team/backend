#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MANIFEST="${1:-${ROOT_DIR}/ci-artifacts/render/combined.yaml}"

if [[ ! -f "${MANIFEST}" ]]; then
  echo "❌ Combined manifest not found: ${MANIFEST}" >&2
  exit 1
fi

echo "::group::Apply CRDs"
kubectl apply -k "${ROOT_DIR}/platform/crds"
echo "::endgroup::"

echo "::group::Server-side dry-run"
kubectl apply --server-side --dry-run=server -f "${MANIFEST}"
echo "::endgroup::"

