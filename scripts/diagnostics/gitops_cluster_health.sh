#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT="dev"
KUBECONFIG_PATH="${KUBECONFIG:-$HOME/.kube/config}"
ARGOCD_NAMESPACE="argocd"
SHOW_EVENTS="false"

usage() {
  cat <<'USAGE'
원격에서 GitOps/클러스터 상태를 빠르게 점검하는 스크립트입니다.

사용법:
  bash scripts/diagnostics/gitops_cluster_health.sh [옵션]

옵션:
  -e, --env <이름>        대상 환경 (기본: dev)
  --kubeconfig <경로>      사용할 kubeconfig 경로 (기본: $HOME/.kube/config)
  --events                 최근 이벤트 20건 출력
  -h, --help               도움말
USAGE
}

log_section() {
  local title="$1"
  printf '\n==== %s ====' "$title"
  printf '\n'
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[오류] '$cmd' 명령을 찾을 수 없습니다." >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -e|--env)
      ENVIRONMENT="$2"
      shift 2
      ;;
    --kubeconfig)
      KUBECONFIG_PATH="$2"
      shift 2
      ;;
    --events)
      SHOW_EVENTS="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "알 수 없는 옵션: $1" >&2
      usage
      exit 1
      ;;
  esac
done

export KUBECONFIG="$KUBECONFIG_PATH"
require_cmd kubectl

ROOT_APP_NAME="${ENVIRONMENT}-root"

log_section "Kubernetes API 연결 확인"
if kubectl cluster-info >/dev/null 2>&1; then
  echo "✅ kubectl cluster-info 성공 ($KUBECONFIG_PATH)"
else
  echo "❌ kubectl cluster-info 실패. KUBECONFIG 경로와 인증 정보를 확인하세요." >&2
  exit 1
fi

log_section "노드 상태"
kubectl get nodes -o wide

log_section "ArgoCD Applications (상태 요약)"
if kubectl get applications -n "$ARGOCD_NAMESPACE" >/dev/null 2>&1; then
  kubectl get applications -n "$ARGOCD_NAMESPACE" \
    -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status,WAVE:.metadata.annotations.argocd\.argoproj\.io/sync-wave \
    --sort-by=.metadata.name
else
  echo "⚠️  ArgoCD Application CR을 가져오지 못했습니다. ArgoCD 네임스페이스/권한을 확인하세요."
fi

log_section "Root App(${ROOT_APP_NAME}) 세부 정보"
if kubectl get application "$ROOT_APP_NAME" -n "$ARGOCD_NAMESPACE" >/dev/null 2>&1; then
  kubectl get application "$ROOT_APP_NAME" -n "$ARGOCD_NAMESPACE" -o yaml | \
    awk '/status:/,/operationState:/'
else
  echo "⚠️  ${ROOT_APP_NAME} Application을 찾을 수 없습니다. root-app 적용 여부를 확인하세요."
fi

log_section "Out-of-sync / 비정상 Application"
if kubectl get applications -n "$ARGOCD_NAMESPACE" >/dev/null 2>&1; then
  kubectl get applications -n "$ARGOCD_NAMESPACE" --no-headers | \
    awk '$2!="Synced" || $3!="Healthy" {print $0}' || true
else
  echo "(생략)"
fi

log_section "비정상 Pod (Running/Succeeded 이외)"
kubectl get pods -A --no-headers | \
  awk '$4 != "Running" && $4 != "Succeeded" {print $0}' || echo "모든 Pod가 Running/Succeeded 상태입니다."

if [[ "$SHOW_EVENTS" == "true" ]]; then
  log_section "최근 이벤트 20건"
  kubectl get events -A --sort-by=.lastTimestamp | tail -n 20 || true
fi

log_section "외부 리소스 (ExternalSecret / CRD)"
if kubectl get externalsecret -A >/dev/null 2>&1; then
  kubectl get externalsecret -A --no-headers | head -n 10
else
  echo "ExternalSecret CR을 조회할 수 없습니다. External Secrets Operator 배포 상태를 확인하세요."
fi

log_section "점검 완료"
echo "환경: ${ENVIRONMENT}"
echo "Kubeconfig: ${KUBECONFIG_PATH}"
