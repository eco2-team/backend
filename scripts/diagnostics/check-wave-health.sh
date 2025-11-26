#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  cat <<'USAGE' >&2
Usage: scripts/diagnostics/check-wave-health.sh <environment> [timeout]

Ensures the Wave 0/10/11 applications (<env>-crds, <env>-external-secrets, <env>-secrets)
are Healthy+Synced via the Argo CD CLI. Requires argocd CLI authentication
to be configured (ARGOCD_SERVER/ARGOCD_AUTH_TOKEN or `argocd login`).
USAGE
  exit 1
fi

ENVIRONMENT="$1"
TIMEOUT="${2:-${ARGOCD_WAVE_WAIT_TIMEOUT:-600}}"
APPS=(
  "${ENVIRONMENT}-crds"
  "${ENVIRONMENT}-external-secrets"
  "${ENVIRONMENT}-secrets"
)

for app in "${APPS[@]}"; do
  echo "🔍 Waiting for ${app} (health + sync) ..."
  argocd app wait "${app}" --health --sync --timeout "${TIMEOUT}"
done

echo "✅ Wave 0/10/11 applications for '${ENVIRONMENT}' are Healthy & Synced."
