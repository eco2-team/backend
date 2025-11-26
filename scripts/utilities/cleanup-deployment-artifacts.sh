#!/usr/bin/env bash
set -euo pipefail

# SeSACTHON 배포 잔여물 정리 유틸리티
# 클러스터 destroy 후 또는 재배포 전 로컬 파일을 정리합니다.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TF_DIR="${REPO_ROOT}/terraform"
ANSIBLE_DIR="${REPO_ROOT}/ansible"
LOGS_DIR="${REPO_ROOT}/logs"

DRY_RUN="false"
CLEANUP_LOGS="false"
CLEANUP_TERRAFORM_STATE="false"
KUBECONFIG_PATH="${KUBECONFIG:-$HOME/.kube/config}"

declare -r LOG_PREFIX="[cleanup]"

usage() {
  cat <<'USAGE'
SeSACTHON 배포 잔여물 정리 유틸리티

사용법:
  bash scripts/utilities/cleanup-deployment-artifacts.sh [옵션]

옵션:
  --dry-run                 실제 삭제 없이 삭제 대상만 표시
  --cleanup-logs            로그 파일도 정리 (7일 이상 된 파일)
  --cleanup-tf-state        Terraform state 파일도 정리 (⚠️ 위험)
  --kubeconfig <경로>       kubeconfig 경로 (기본: $HOME/.kube/config)
  -h, --help                도움말 출력

설명:
  이 스크립트는 다음 항목들을 정리합니다:
  - Ansible inventory 파일 (hosts.ini, hosts.tmp)
  - kubeadm join 임시 스크립트 (/tmp/kubeadm_join_command.sh)
  - Terraform 백업 파일 (terraform.tfstate.backup, tfplan*)
  - kubeconfig 내 클러스터 컨텍스트 (kubernetes-admin@kubernetes)
  - (옵션) 로그 파일 (7일 이상)
  - (옵션) Terraform state 파일 (terraform.tfstate)

⚠️  주의:
  --cleanup-tf-state 옵션은 Terraform이 인프라 상태를 추적할 수 없게 만듭니다.
  반드시 destroy 후에만 사용하세요!
USAGE
}

log() {
  printf '%s %s\n' "${LOG_PREFIX}" "$*"
}

remove_file() {
  local file="$1"
  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "${LOG_PREFIX} [DRY-RUN] 삭제 예정: ${file}"
  else
    if [[ -f "${file}" ]]; then
      rm -f "${file}"
      log "✓ 삭제: ${file}"
    fi
  fi
}

remove_pattern() {
  local pattern="$1"
  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "${LOG_PREFIX} [DRY-RUN] 삭제 예정 (패턴): ${pattern}"
    find "${TF_DIR}" -name "${pattern}" 2>/dev/null || true
  else
    local count=$(find "${TF_DIR}" -name "${pattern}" -delete -print 2>/dev/null | wc -l)
    if [[ "${count}" -gt 0 ]]; then
      log "✓ 삭제: ${pattern} (${count}개 파일)"
    fi
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    --cleanup-logs)
      CLEANUP_LOGS="true"
      shift
      ;;
    --cleanup-tf-state)
      CLEANUP_TERRAFORM_STATE="true"
      shift
      ;;
    --kubeconfig)
      KUBECONFIG_PATH="$2"
      shift 2
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

if [[ "${DRY_RUN}" == "true" ]]; then
  log "🔍 DRY-RUN 모드: 실제 삭제는 하지 않습니다."
fi

log "배포 잔여물 정리 시작..."

# 1. Ansible 관련 파일
log "1️⃣ Ansible 임시 파일 정리"
remove_file "${ANSIBLE_DIR}/inventory/hosts.ini"
remove_file "${ANSIBLE_DIR}/inventory/hosts.tmp"
remove_file "/tmp/kubeadm_join_command.sh"

# 2. Terraform 백업 파일
log "2️⃣ Terraform 백업 파일 정리"
remove_file "${TF_DIR}/terraform.tfstate.backup"
remove_pattern "tfplan*"

# 3. Terraform state (선택적, 위험)
if [[ "${CLEANUP_TERRAFORM_STATE}" == "true" ]]; then
  log "3️⃣ Terraform state 파일 정리 (⚠️ 위험)"
  if [[ "${DRY_RUN}" != "true" ]]; then
    read -r -p "${LOG_PREFIX} ⚠️  정말 Terraform state를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다! [yes/NO] " answer
    if [[ "${answer}" != "yes" ]]; then
      log "Terraform state 삭제를 건너뜁니다."
    else
      remove_file "${TF_DIR}/terraform.tfstate"
      remove_file "${TF_DIR}/.terraform.lock.hcl"
      if [[ "${DRY_RUN}" != "true" ]] && [[ -d "${TF_DIR}/.terraform" ]]; then
        rm -rf "${TF_DIR}/.terraform"
        log "✓ 삭제: ${TF_DIR}/.terraform/"
      fi
    fi
  else
    echo "${LOG_PREFIX} [DRY-RUN] 삭제 예정: ${TF_DIR}/terraform.tfstate"
    echo "${LOG_PREFIX} [DRY-RUN] 삭제 예정: ${TF_DIR}/.terraform/"
  fi
fi

# 4. 로그 파일 (선택적)
if [[ "${CLEANUP_LOGS}" == "true" ]]; then
  log "4️⃣ 로그 파일 정리 (7일 이상 된 파일)"
  if [[ -d "${LOGS_DIR}" ]]; then
    if [[ "${DRY_RUN}" == "true" ]]; then
      echo "${LOG_PREFIX} [DRY-RUN] 삭제 예정 (로그):"
      find "${LOGS_DIR}" -type f -name "*.log" -mtime +7 2>/dev/null || true
    else
      local log_count=$(find "${LOGS_DIR}" -type f -name "*.log" -mtime +7 -delete -print 2>/dev/null | wc -l)
      if [[ "${log_count}" -gt 0 ]]; then
        log "✓ 삭제: ${log_count}개의 오래된 로그 파일"
      else
        log "  오래된 로그 파일 없음"
      fi
    fi
  fi
fi

# 5. kubeconfig 정리
log "5️⃣ kubeconfig 클러스터 컨텍스트 정리"
if [[ -f "${KUBECONFIG_PATH}" ]] && command -v kubectl >/dev/null 2>&1; then
  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "${LOG_PREFIX} [DRY-RUN] 삭제 예정: kubeconfig 내 kubernetes 컨텍스트"
  else
    kubectl config delete-context "kubernetes-admin@kubernetes" 2>/dev/null && log "✓ 삭제: kubernetes-admin@kubernetes 컨텍스트" || true
    kubectl config delete-cluster kubernetes 2>/dev/null && log "✓ 삭제: kubernetes 클러스터" || true
    kubectl config delete-user kubernetes-admin 2>/dev/null && log "✓ 삭제: kubernetes-admin 사용자" || true
  fi
else
  log "  kubeconfig 또는 kubectl을 찾을 수 없어 건너뜁니다."
fi

if [[ "${DRY_RUN}" == "true" ]]; then
  log ""
  log "🔍 DRY-RUN 완료. 실제 삭제를 원하면 --dry-run 옵션을 제거하세요."
else
  log ""
  log "✅ 배포 잔여물 정리 완료!"
fi
