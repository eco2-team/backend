#!/bin/bash

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SSH to Any Kubernetes Node
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -euo pipefail

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Configuration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TERRAFORM_DIR="${PROJECT_ROOT}/terraform"
ANSIBLE_DIR="${PROJECT_ROOT}/ansible"
SSH_KEY="${HOME}/.ssh/id_rsa"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Functions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

log_info() {
    echo -e "${BLUE}ℹ️  INFO${NC}: $*"
}

log_success() {
    echo -e "${GREEN}✅${NC} $*"
}

log_error() {
    echo -e "${RED}❌ ERROR${NC}: $*"
}

log_warning() {
    echo -e "${YELLOW}⚠️  WARNING${NC}: $*"
}

# Resolve node alias to actual node name
resolve_node_alias() {
    local input="$1"
    
    # Direct matches
    case "$input" in
        # Master
        master|m) echo "master" ;;
        
        # API Nodes
        auth) echo "api_auth" ;;
        my) echo "api_my" ;;
        scan) echo "api_scan" ;;
        character) echo "api_character" ;;
        location) echo "api_location" ;;
        info) echo "api_info" ;;
        chat) echo "api_chat" ;;
        
        # Worker Nodes
        worker-storage|storage|ws) echo "worker_storage" ;;
        worker-ai|ai|wa) echo "worker_ai" ;;
        
        # Infrastructure Nodes
        postgresql|postgres|pg|db) echo "postgresql" ;;
        redis) echo "redis" ;;
        rabbitmq|rabbit|mq) echo "rabbitmq" ;;
        monitoring|mon) echo "monitoring" ;;
        
        # Default: return input as-is
        *) echo "$input" ;;
    esac
}

show_usage() {
    cat << 'EOF'
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔗 SSH to Kubernetes Node
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Usage:
  ./ssh-master.sh [node]
  ./ssh-master.sh          # Master 노드 (기본값)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 Available Nodes:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔧 Control Plane:
  master, m                        # Master 노드

📡 API Nodes (Phase 1-3):
  auth                             # API Auth
  my                               # API My
  scan                             # API Scan
  character                        # API Character
  location                         # API Location
  info                             # API Info
  chat                             # API Chat

⚙️ Worker Nodes (Phase 4):
  worker-storage, storage, ws      # Storage Worker
  worker-ai, ai, wa                # AI Worker

🗄️ Infrastructure Nodes:
  postgresql, postgres, pg, db     # PostgreSQL
  redis                            # Redis
  rabbitmq, rabbit, mq             # RabbitMQ
  monitoring, mon                  # Monitoring

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 Examples:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ./ssh-master.sh              # Master 노드
  ./ssh-master.sh m            # Master 노드 (짧은 형식)
  ./ssh-master.sh auth         # API Auth 노드
  ./ssh-master.sh pg           # PostgreSQL 노드
  ./ssh-master.sh mon          # Monitoring 노드

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EOF
    exit 0
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Get Node IP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

get_node_ip_from_terraform() {
    local node_name="$1"
    cd "${TERRAFORM_DIR}"
    terraform output -raw "${node_name}_public_ip" 2>/dev/null || echo ""
}

get_node_ip_from_inventory() {
    local node_name="$1"
    if [[ ! -f "${ANSIBLE_DIR}/inventory/hosts.ini" ]]; then
        echo ""
        return
    fi
    
    # Convert node_name to inventory group name
    local group_name="${node_name//_/-}"  # api_auth -> api-auth
    
    # Search for the node in inventory
    grep -A 1 "\[${group_name}\]" "${ANSIBLE_DIR}/inventory/hosts.ini" 2>/dev/null | \
        grep -oP '\d+\.\d+\.\d+\.\d+' | head -1 || echo ""
}

list_all_nodes() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📋 Available Nodes in Cluster"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    cd "${TERRAFORM_DIR}"
    
    # Get all node IPs
    local master_ip=$(terraform output -raw master_public_ip 2>/dev/null || echo "N/A")
    
    echo -e "${CYAN}🔧 Control Plane:${NC}"
    printf "  %-20s %s\n" "master" "$master_ip"
    echo ""
    
    echo -e "${CYAN}📡 API Nodes:${NC}"
    for api in auth my scan character location info chat; do
        local ip=$(terraform output -raw "api_${api}_public_ip" 2>/dev/null || echo "N/A")
        printf "  %-20s %s\n" "$api" "$ip"
    done
    echo ""
    
    echo -e "${CYAN}⚙️ Worker Nodes:${NC}"
    local ws_ip=$(terraform output -raw worker_storage_public_ip 2>/dev/null || echo "N/A")
    local wa_ip=$(terraform output -raw worker_ai_public_ip 2>/dev/null || echo "N/A")
    printf "  %-20s %s\n" "worker-storage" "$ws_ip"
    printf "  %-20s %s\n" "worker-ai" "$wa_ip"
    echo ""
    
    echo -e "${CYAN}🗄️ Infrastructure Nodes:${NC}"
    local pg_ip=$(terraform output -raw postgresql_public_ip 2>/dev/null || echo "N/A")
    local redis_ip=$(terraform output -raw redis_public_ip 2>/dev/null || echo "N/A")
    local mq_ip=$(terraform output -raw rabbitmq_public_ip 2>/dev/null || echo "N/A")
    local mon_ip=$(terraform output -raw monitoring_public_ip 2>/dev/null || echo "N/A")
    printf "  %-20s %s\n" "postgresql" "$pg_ip"
    printf "  %-20s %s\n" "redis" "$redis_ip"
    printf "  %-20s %s\n" "rabbitmq" "$mq_ip"
    printf "  %-20s %s\n" "monitoring" "$mon_ip"
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

get_quick_commands_for_node() {
    local node_type="$1"
    
    case "$node_type" in
        master)
            cat << 'EOF'
📋 Quick Commands (Master):
  kubectl get nodes -o wide              # 노드 상태 확인
  kubectl get pods -A                    # 모든 Pod 확인
  kubectl get svc -A                     # 모든 Service 확인
  kubectl top nodes                      # 노드 리소스 사용량
  kubectl describe node <node-name>      # 노드 상세 정보
EOF
            ;;
        api_*)
            cat << 'EOF'
📋 Quick Commands (API Node):
  sudo systemctl status kubelet          # Kubelet 상태
  sudo journalctl -u kubelet -f          # Kubelet 로그
  kubectl get pods -o wide               # 이 노드의 Pod 확인 (Master에서)
  docker ps                              # 실행 중인 컨테이너
EOF
            ;;
        worker_*)
            cat << 'EOF'
📋 Quick Commands (Worker Node):
  sudo systemctl status kubelet          # Kubelet 상태
  sudo journalctl -u kubelet -f          # Kubelet 로그
  kubectl get pods -o wide               # 이 노드의 Pod 확인 (Master에서)
  docker ps                              # 실행 중인 컨테이너
EOF
            ;;
        postgresql)
            cat << 'EOF'
📋 Quick Commands (PostgreSQL):
  sudo systemctl status postgresql       # PostgreSQL 상태
  sudo -u postgres psql                  # PostgreSQL 접속
  kubectl get pods -o wide               # 이 노드의 Pod 확인 (Master에서)
EOF
            ;;
        redis)
            cat << 'EOF'
📋 Quick Commands (Redis):
  redis-cli ping                         # Redis 연결 테스트
  redis-cli INFO                         # Redis 정보
  kubectl get pods -o wide               # 이 노드의 Pod 확인 (Master에서)
EOF
            ;;
        rabbitmq)
            cat << 'EOF'
📋 Quick Commands (RabbitMQ):
  sudo rabbitmqctl status                # RabbitMQ 상태
  sudo rabbitmqctl list_queues           # 큐 목록
  kubectl get pods -o wide               # 이 노드의 Pod 확인 (Master에서)
EOF
            ;;
        monitoring)
            cat << 'EOF'
📋 Quick Commands (Monitoring):
  kubectl get pods -n monitoring         # Monitoring Pod 확인 (Master에서)
  kubectl logs -n monitoring <pod>       # Pod 로그 확인 (Master에서)
  docker ps                              # 실행 중인 컨테이너
EOF
            ;;
        *)
            cat << 'EOF'
📋 Quick Commands:
  sudo systemctl status kubelet          # Kubelet 상태
  kubectl get pods -o wide               # 이 노드의 Pod 확인 (Master에서)
EOF
            ;;
    esac
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

main() {
    # Parse arguments
    local target_node="master"  # Default to master
    
    if [[ $# -gt 0 ]]; then
        case "$1" in
            -h|--help|help)
                show_usage
                ;;
            -l|--list|list)
                list_all_nodes
                exit 0
                ;;
            *)
                target_node="$1"
                ;;
        esac
    fi
    
    # Resolve alias
    local node_name=$(resolve_node_alias "$target_node")
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔗 Connecting to Kubernetes Node: ${node_name}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Get Node IP
    log_info "${node_name} IP 조회 중..."
    NODE_IP=$(get_node_ip_from_terraform "${node_name}")
    
    if [[ -z "${NODE_IP}" ]]; then
        log_warning "Terraform output에서 IP를 찾을 수 없습니다. Inventory 파일 확인 중..."
        NODE_IP=$(get_node_ip_from_inventory "${node_name}")
    fi

    if [[ -z "${NODE_IP}" ]]; then
        log_error "${node_name} 노드 IP를 찾을 수 없습니다"
        echo ""
        log_info "사용 가능한 노드 목록 보기: $0 --list"
        log_info "도움말 보기: $0 --help"
        exit 1
    fi

    log_success "${node_name} IP: ${NODE_IP}"

    # Check SSH Key
    if [[ ! -f "${SSH_KEY}" ]]; then
        log_error "SSH 키를 찾을 수 없습니다: ${SSH_KEY}"
        exit 1
    fi

    log_success "SSH 키 확인 완료"
    echo ""

    # Display connection info
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "노드: ${node_name}"
    log_info "주소: ubuntu@${NODE_IP}"
    log_info "SSH Key: ${SSH_KEY}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Display node-specific commands
    get_quick_commands_for_node "${node_name}"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Connect via SSH
    ssh -i "${SSH_KEY}" \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR \
        ubuntu@"${NODE_IP}"
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Entry Point
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

main "$@"

