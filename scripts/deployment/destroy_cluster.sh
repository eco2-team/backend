#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TF_DIR="${REPO_ROOT}/terraform"
ANSIBLE_DIR="${REPO_ROOT}/ansible"
CLUSTERS_DIR="${REPO_ROOT}/clusters"
LOGS_DIR="${REPO_ROOT}/logs"

ENVIRONMENT="dev"
KUBECONFIG_PATH="${KUBECONFIG:-$HOME/.kube/config}"
AUTO_APPROVE="false"
DELETE_ROOT_APP="false"
CLEANUP_ALL="false"

declare -r LOG_PREFIX="[destroy]"

usage() {
  cat <<'USAGE'
SeSACTHON GitOps 클러스터 종료 스크립트

사용법:
  bash scripts/deployment/destroy_cluster.sh [옵션]

옵션:
  -e, --env <이름>         대상 환경 (기본: dev)
  --kubeconfig <경로>       root-app 삭제 시 사용할 kubeconfig 경로
  --delete-root-app         Terraform destroy 전 ArgoCD root-app 삭제
  --cleanup-all             Ansible/Terraform 임시 파일 모두 정리
  -y, --yes                 Terraform destroy를 자동 승인
  -h, --help                도움말 출력

환경 변수:
  TF_VAR_FILE               명시 시 해당 tfvars 파일 사용 (옵션)
USAGE
}

log() {
  printf '%s %s\n' "${LOG_PREFIX}" "$*"
}

require_cmd() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "${LOG_PREFIX} 오류: '${cmd}' 명령을 찾을 수 없습니다." >&2
    exit 1
  fi
}

resolve_tfvars_file() {
  if [[ -n "${TF_VAR_FILE:-}" ]]; then
    printf '%s' "${TF_VAR_FILE}"
    return 0
  fi

  local env_name="$1"
  local candidates=(
    "${TF_DIR}/env/${env_name}.tfvars"
    "${TF_DIR}/${env_name}.tfvars"
    "${TF_DIR}/terraform.tfvars"
  )

  for file in "${candidates[@]}"; do
    if [[ -f "${file}" ]]; then
      printf '%s' "${file}"
      return 0
    fi
  done

  return 1
}

confirm_destroy() {
  if [[ "${AUTO_APPROVE}" == "true" ]]; then
    return 0
  fi

  read -r -p "${LOG_PREFIX} 경고: ${ENVIRONMENT} 환경의 모든 리소스를 삭제합니다. 계속할까요? [y/N] " answer
  case "${answer}" in
    y|Y|yes|YES)
      return 0
      ;;
    *)
      log "요청을 취소했습니다."
      exit 0
      ;;
  esac
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
    --delete-root-app)
      DELETE_ROOT_APP="true"
      shift
      ;;
    --cleanup-all)
      CLEANUP_ALL="true"
      shift
      ;;
    -y|--yes)
      AUTO_APPROVE="true"
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

TF_VARS_FILE="$(resolve_tfvars_file "${ENVIRONMENT}")" || {
  echo "${LOG_PREFIX} 오류: '${ENVIRONMENT}' 환경에 사용할 tfvars 파일을 찾을 수 없습니다." >&2
  exit 1
}

require_cmd terraform

if [[ "${DELETE_ROOT_APP}" == "true" ]]; then
  require_cmd kubectl
  ROOT_APP_FILE="${CLUSTERS_DIR}/${ENVIRONMENT}/root-app.yaml"
  if [[ ! -f "${ROOT_APP_FILE}" ]]; then
    echo "${LOG_PREFIX} 경고: ${ROOT_APP_FILE} 파일이 없어 root-app 삭제를 건너뜁니다." >&2
  elif [[ ! -f "${KUBECONFIG_PATH}" ]]; then
    echo "${LOG_PREFIX} 경고: kubeconfig '${KUBECONFIG_PATH}'를 찾을 수 없어 root-app 삭제를 건너뜁니다." >&2
  else
    log "ArgoCD root-app 삭제 (${ROOT_APP_FILE})"
    kubectl --kubeconfig "${KUBECONFIG_PATH}" delete -n argocd -f "${ROOT_APP_FILE}" --ignore-not-found
  fi
fi

confirm_destroy

log "Terraform destroy 실행 (env=${ENVIRONMENT})"
pushd "${TF_DIR}" >/dev/null
terraform init -input=false >/dev/null
if [[ "${AUTO_APPROVE}" == "true" ]]; then
  terraform destroy -input=false -auto-approve -var-file "${TF_VARS_FILE}"
else
  terraform destroy -input=false -var-file "${TF_VARS_FILE}"
fi
popd >/dev/null

# 정리 작업
if [[ "${CLEANUP_ALL}" == "true" ]]; then
  log "로컬 잔여 파일 정리 시작..."

  # 1. Ansible 관련 파일 정리
  if [[ -d "${ANSIBLE_DIR}" ]]; then
    log "Ansible 임시 파일 삭제"
    rm -f "${ANSIBLE_DIR}/inventory/hosts.ini" 2>/dev/null || true
    rm -f "${ANSIBLE_DIR}/inventory/hosts.tmp" 2>/dev/null || true
    rm -f /tmp/kubeadm_join_command.sh 2>/dev/null || true
  fi

  # 2. Terraform 백업 파일 정리
  if [[ -d "${TF_DIR}" ]]; then
    log "Terraform 백업 파일 삭제"
    rm -f "${TF_DIR}/terraform.tfstate.backup" 2>/dev/null || true
    rm -f "${TF_DIR}/tfplan"* 2>/dev/null || true
  fi

  # 3. 로그 파일 정리 (선택적)
  if [[ -d "${LOGS_DIR}" ]]; then
    log "로그 파일 정리 (7일 이상 된 파일)"
    find "${LOGS_DIR}" -type f -name "*.log" -mtime +7 -delete 2>/dev/null || true
  fi

  # 4. 로컬 kubeconfig에서 클러스터 컨텍스트 제거 (안전하게)
  if [[ -f "${KUBECONFIG_PATH}" ]] && command -v kubectl >/dev/null 2>&1; then
    log "kubeconfig에서 클러스터 컨텍스트 제거 시도"
    kubectl config delete-context "kubernetes-admin@kubernetes" 2>/dev/null || true
    kubectl config delete-cluster kubernetes 2>/dev/null || true
    kubectl config delete-user kubernetes-admin 2>/dev/null || true
  fi

  log "로컬 파일 정리 완료"
fi

log "클러스터 리소스 삭제가 완료되었습니다."
if [[ "${CLEANUP_ALL}" != "true" ]]; then
  log "💡 팁: --cleanup-all 옵션으로 로컬 임시 파일도 정리할 수 있습니다."
fi
