#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TF_DIR="${REPO_ROOT}/terraform"
ANSIBLE_DIR="${REPO_ROOT}/ansible"
CLUSTERS_DIR="${REPO_ROOT}/clusters"
ANSIBLE_INVENTORY_PATH="${ANSIBLE_DIR}/inventory/hosts.ini"

ENVIRONMENT="dev"
KUBECONFIG_PATH="${KUBECONFIG:-$HOME/.kube/config}"
SKIP_TERRAFORM="false"
SKIP_ANSIBLE="false"
SKIP_ARGOCD="false"
SKIP_PREFLIGHT_CHECK="false"

declare -r LOG_PREFIX="[bootstrap]"
terraform_initialized="false"

usage() {
  cat <<'USAGE'
SeSACTHON GitOps 부트스트랩 스크립트

사용법:
  bash scripts/deployment/bootstrap_cluster.sh [옵션]

옵션:
  -e, --env <이름>         사용할 환경 (dev 또는 prod, 기본: dev) — Terraform tfvars, Ansible vars 자동 분기
  --kubeconfig <경로>       kubectl이 사용할 kubeconfig 경로 (기본: $HOME/.kube/config)
  --skip-terraform          Terraform apply 단계 건너뛰기
  --skip-ansible            Ansible 부트스트랩 단계 건너뛰기
  --skip-argocd             ArgoCD root-app 적용 건너뛰기
  --skip-preflight-check    사전 점검 건너뛰기 (잔여 파일 체크 등)
  -h, --help                도움말 출력

환경 변수:
  TF_VAR_FILE               명시하면 해당 tfvars 파일을 사용 (옵션)
  ANSIBLE_EXTRA_VARS        ansible-playbook --extra-vars 전달값 (옵션)
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

terraform_init_once() {
  if [[ "${terraform_initialized}" == "true" ]]; then
    return 0
  fi
  log "Terraform backend 초기화 (${TF_DIR})"
  pushd "${TF_DIR}" >/dev/null
  terraform init -input=false >/dev/null
  popd >/dev/null
  terraform_initialized="true"
}

generate_ansible_inventory() {
  terraform_init_once
  mkdir -p "$(dirname "${ANSIBLE_INVENTORY_PATH}")"
  pushd "${TF_DIR}" >/dev/null
  terraform output -raw ansible_inventory > "${ANSIBLE_INVENTORY_PATH}"
  popd >/dev/null
  log "Ansible inventory를 '${ANSIBLE_INVENTORY_PATH}'에 생성했습니다."
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
    --skip-terraform)
      SKIP_TERRAFORM="true"
      shift
      ;;
    --skip-ansible)
      SKIP_ANSIBLE="true"
      shift
      ;;
    --skip-argocd)
      SKIP_ARGOCD="true"
      shift
      ;;
    --skip-preflight-check)
      SKIP_PREFLIGHT_CHECK="true"
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
if [[ "${SKIP_ANSIBLE}" != "true" ]]; then
  require_cmd ansible-playbook
fi
if [[ "${SKIP_ARGOCD}" != "true" ]]; then
  require_cmd kubectl
fi

log "Target environment: ${ENVIRONMENT}"
log "tfvars 파일: ${TF_VARS_FILE}"

# 사전 점검: 이전 배포 잔여물 확인
if [[ "${SKIP_PREFLIGHT_CHECK}" != "true" ]]; then
  log "사전 점검 실행 중..."

  has_remnants="false"

  # Terraform state 확인
  if [[ -f "${TF_DIR}/terraform.tfstate" ]]; then
    pushd "${TF_DIR}" >/dev/null
    resource_count=$(terraform show -json 2>/dev/null | grep -c '"type":' || echo "0")
    popd >/dev/null
    if [[ "${resource_count}" -gt 0 ]]; then
      echo "${LOG_PREFIX} ⚠️  경고: 기존 Terraform 리소스가 ${resource_count}개 존재합니다." >&2
      has_remnants="true"
    fi
  fi

  # Ansible inventory 잔여물 확인
  if [[ -f "${ANSIBLE_INVENTORY_PATH}" ]]; then
    echo "${LOG_PREFIX} ⚠️  경고: 이전 Ansible inventory 파일이 존재합니다: ${ANSIBLE_INVENTORY_PATH}" >&2
    has_remnants="true"
  fi

  # /tmp의 kubeadm join 스크립트 확인
  if [[ -f "/tmp/kubeadm_join_command.sh" ]]; then
    echo "${LOG_PREFIX} ⚠️  경고: 이전 kubeadm join 스크립트가 존재합니다: /tmp/kubeadm_join_command.sh" >&2
    has_remnants="true"
  fi

  if [[ "${has_remnants}" == "true" ]]; then
    echo ""
    echo "${LOG_PREFIX} 💡 권장사항:" >&2
    echo "  1. 기존 클러스터가 실행 중이면 먼저 삭제하세요:" >&2
    echo "     bash scripts/deployment/destroy_cluster.sh --cleanup-all -y" >&2
    echo ""
    echo "  2. 또는 --skip-preflight-check 옵션으로 이 경고를 무시할 수 있습니다." >&2
    echo ""
    read -r -p "${LOG_PREFIX} 계속 진행하시겠습니까? [y/N] " answer
    case "${answer}" in
      y|Y|yes|YES)
        log "사용자 확인: 계속 진행합니다."
        ;;
      *)
        log "작업을 취소했습니다."
        exit 0
        ;;
    esac
  else
    log "✅ 사전 점검 통과: 잔여 파일 없음"
  fi
fi

if [[ "${SKIP_TERRAFORM}" != "true" ]]; then
  terraform_init_once
  log "Terraform apply 실행"
  pushd "${TF_DIR}" >/dev/null
  terraform apply -input=false -auto-approve -var-file "${TF_VARS_FILE}"
  popd >/dev/null
else
  log "Terraform apply 건너뜀 (--skip-terraform)"
fi

if [[ "${SKIP_ANSIBLE}" != "true" ]]; then
  generate_ansible_inventory
  log "Ansible Playbook 실행"
  pushd "${ANSIBLE_DIR}" >/dev/null
  export ANSIBLE_CONFIG="${ANSIBLE_DIR}/ansible.cfg"
  export ANSIBLE_HOST_KEY_CHECKING=${ANSIBLE_HOST_KEY_CHECKING:-False}
  ansible_playbook_cmd=(ansible-playbook -i "${ANSIBLE_INVENTORY_PATH}" site.yml)

  # 1) 기본 env 변수 (항상 전달)
  ansible_playbook_cmd+=(--extra-vars "cluster_env=${ENVIRONMENT}")

  # 2) env 전용 vars 파일이 있으면 함께 전달 (예: ansible/group_vars/dev.yml)
  ENV_VARS_FILE="${ANSIBLE_DIR}/group_vars/${ENVIRONMENT}.yml"
  if [[ -f "${ENV_VARS_FILE}" ]]; then
    log "Ansible env vars 적용: ${ENV_VARS_FILE}"
    ansible_playbook_cmd+=(--extra-vars "@${ENV_VARS_FILE}")
  else
    log "Ansible env vars 파일(${ENV_VARS_FILE})이 없어 건너뜁니다."
  fi

  # 3) 사용자 정의 extra vars(있다면) 마지막에 전달해 최종 override 가능
  if [[ -n "${ANSIBLE_EXTRA_VARS:-}" ]]; then
    ansible_playbook_cmd+=(--extra-vars "${ANSIBLE_EXTRA_VARS}")
  fi

  "${ansible_playbook_cmd[@]}"
  popd >/dev/null
else
  log "Ansible 단계 건너뜀 (--skip-ansible)"
fi

if [[ "${SKIP_ARGOCD}" != "true" ]]; then
  ROOT_APP_FILE="${CLUSTERS_DIR}/${ENVIRONMENT}/root-app.yaml"
  if [[ ! -f "${ROOT_APP_FILE}" ]]; then
    echo "${LOG_PREFIX} 오류: ${ROOT_APP_FILE} 파일을 찾을 수 없습니다." >&2
    exit 1
  fi
  if [[ ! -f "${KUBECONFIG_PATH}" ]]; then
    echo "${LOG_PREFIX} 오류: kubeconfig '${KUBECONFIG_PATH}'가 존재하지 않습니다. --kubeconfig 옵션 또는 KUBECONFIG 환경 변수를 확인하세요." >&2
    exit 1
  fi
  log "기존 ArgoCD root-app 삭제 (${ROOT_APP_FILE})"
  kubectl --kubeconfig "${KUBECONFIG_PATH}" delete -n argocd -f "${ROOT_APP_FILE}" --ignore-not-found || true
  log "ArgoCD root-app 적용 (${ROOT_APP_FILE})"
  kubectl --kubeconfig "${KUBECONFIG_PATH}" apply -n argocd -f "${ROOT_APP_FILE}"
else
  log "ArgoCD root-app 적용 건너뜀 (--skip-argocd)"
fi

log "모든 단계가 완료되었습니다."
