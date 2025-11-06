#!/bin/bash
# SSH 키 생성 및 설정 가이드 스크립트

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔑 SSH 키 생성 및 설정 가이드"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 색상 코드
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SSH_KEY_PATH="$HOME/.ssh/sesacthon.pem"
SSH_KEY_NAME="sesacthon"

echo "이 스크립트는 두 가지 방법을 제공합니다:"
echo ""
echo -e "${BLUE}1. AWS에서 기존 키 페어 다운로드 (권장)${NC}"
echo "   - 이미 AWS에 'sesacthon' 키 페어가 있는 경우"
echo "   - 팀원과 공유된 키를 사용하는 경우"
echo ""
echo -e "${BLUE}2. AWS에 새 키 페어 생성${NC}"
echo "   - 처음 시작하는 경우"
echo "   - 기존 키를 분실한 경우 (주의: 기존 인스턴스 접근 불가)"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# AWS CLI 확인
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI가 설치되어 있지 않습니다!${NC}"
    echo ""
    echo "AWS CLI 설치 방법:"
    echo ""
    echo "  macOS:"
    echo "    brew install awscli"
    echo ""
    echo "  Linux:"
    echo "    curl \"https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip\" -o \"awscliv2.zip\""
    echo "    unzip awscliv2.zip"
    echo "    sudo ./aws/install"
    echo ""
    exit 1
fi

# AWS 자격 증명 확인
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}❌ AWS 자격 증명이 설정되지 않았습니다!${NC}"
    echo ""
    echo "AWS 자격 증명 설정 방법:"
    echo ""
    echo "  aws configure"
    echo ""
    echo "  또는 환경변수 설정:"
    echo "  export AWS_ACCESS_KEY_ID=..."
    echo "  export AWS_SECRET_ACCESS_KEY=..."
    echo ""
    exit 1
fi

echo -e "${GREEN}✅ AWS CLI 및 자격 증명 확인 완료${NC}"
echo ""

# 리전 설정
AWS_REGION="${AWS_REGION:-ap-northeast-2}"
echo "AWS 리전: $AWS_REGION"
echo ""

# 기존 키 페어 확인
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【AWS 키 페어 확인】"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if aws ec2 describe-key-pairs --key-names "$SSH_KEY_NAME" --region "$AWS_REGION" &> /dev/null; then
    echo -e "${YELLOW}⚠️  AWS에 '$SSH_KEY_NAME' 키 페어가 이미 존재합니다!${NC}"
    echo ""
    echo "옵션:"
    echo ""
    echo -e "${BLUE}1. 기존 키 파일이 있다면 ~/.ssh/sesacthon.pem에 배치${NC}"
    echo "   (팀원에게 받거나 백업에서 복원)"
    echo ""
    echo -e "${BLUE}2. 기존 키 페어를 삭제하고 새로 생성 (주의!)${NC}"
    echo "   (기존 인스턴스에 접근 불가하게 됩니다)"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    read -p "기존 키 페어를 삭제하고 새로 생성하시겠습니까? (yes/no): " CONFIRM
    
    if [ "$CONFIRM" = "yes" ]; then
        echo ""
        echo "기존 키 페어 삭제 중..."
        aws ec2 delete-key-pair --key-name "$SSH_KEY_NAME" --region "$AWS_REGION"
        echo -e "${GREEN}✅ 기존 키 페어 삭제 완료${NC}"
        echo ""
    else
        echo ""
        echo -e "${YELLOW}작업을 취소했습니다.${NC}"
        echo ""
        echo "다음 중 하나를 선택하세요:"
        echo ""
        echo "1. 팀원에게 sesacthon.pem 파일 받기"
        echo "2. 백업에서 sesacthon.pem 복원"
        echo "3. 다른 키 이름 사용 (terraform/variables.tf에서 key_name 변경)"
        echo ""
        exit 0
    fi
else
    echo -e "${GREEN}✅ AWS에 '$SSH_KEY_NAME' 키 페어가 없습니다 (새로 생성 가능)${NC}"
    echo ""
fi

# 새 키 페어 생성
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "【새 SSH 키 페어 생성】"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# .ssh 디렉토리 생성
mkdir -p "$HOME/.ssh"

echo "AWS에 '$SSH_KEY_NAME' 키 페어 생성 중..."
echo ""

# 키 페어 생성 및 저장
aws ec2 create-key-pair \
    --key-name "$SSH_KEY_NAME" \
    --region "$AWS_REGION" \
    --query 'KeyMaterial' \
    --output text > "$SSH_KEY_PATH"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ SSH 키 페어 생성 완료!${NC}"
    echo ""
    echo "키 파일 위치: $SSH_KEY_PATH"
    echo ""
    
    # 권한 설정
    chmod 400 "$SSH_KEY_PATH"
    echo -e "${GREEN}✅ 파일 권한 설정 완료 (400)${NC}"
    echo ""
    
    # 키 정보 출력
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "【SSH 키 정보】"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  키 이름: $SSH_KEY_NAME"
    echo "  리전: $AWS_REGION"
    echo "  파일 경로: $SSH_KEY_PATH"
    echo "  파일 권한: $(stat -f "%OLp" "$SSH_KEY_PATH" 2>/dev/null || stat -c "%a" "$SSH_KEY_PATH" 2>/dev/null)"
    echo ""
    
    # 지문 확인
    echo "AWS 키 지문:"
    aws ec2 describe-key-pairs \
        --key-names "$SSH_KEY_NAME" \
        --region "$AWS_REGION" \
        --query 'KeyPairs[0].KeyFingerprint' \
        --output text
    echo ""
    
    echo "로컬 키 지문:"
    ssh-keygen -l -f "$SSH_KEY_PATH" 2>/dev/null | awk '{print $2}' || echo "(확인 불가)"
    echo ""
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    # 백업 권장
    echo -e "${YELLOW}⚠️  중요: 이 키 파일을 안전한 곳에 백업하세요!${NC}"
    echo ""
    echo "백업 방법:"
    echo ""
    echo "  1. 다른 위치에 복사:"
    echo "     cp $SSH_KEY_PATH ~/Backup/sesacthon.pem.backup"
    echo ""
    echo "  2. 암호화하여 저장:"
    echo "     gpg -c $SSH_KEY_PATH"
    echo ""
    echo "  3. 팀원과 공유 (안전한 방법으로):"
    echo "     - 1Password, LastPass 등 비밀번호 관리자"
    echo "     - 암호화된 이메일"
    echo "     - Slack 비공개 메시지 (권장하지 않음)"
    echo ""
    
    # 테스트
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "【SSH 키 테스트】"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "클러스터 구축 후 다음 명령어로 SSH 접속 테스트:"
    echo ""
    echo "  ssh -i $SSH_KEY_PATH ubuntu@<MASTER_PUBLIC_IP>"
    echo ""
    echo "예시:"
    echo "  ssh -i $SSH_KEY_PATH ubuntu@52.79.238.50"
    echo ""
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${GREEN}✅ SSH 키 설정 완료!${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "이제 다음 단계로 진행하세요:"
    echo ""
    echo "  1. Rebuild 전 체크:"
    echo "     ./scripts/cluster/pre-rebuild-check.sh"
    echo ""
    echo "  2. 클러스터 구축:"
    echo "     ./scripts/cluster/build-cluster.sh"
    echo ""
else
    echo -e "${RED}❌ SSH 키 페어 생성 실패!${NC}"
    echo ""
    echo "오류를 확인하세요:"
    echo "  - AWS 권한 확인 (ec2:CreateKeyPair)"
    echo "  - 리전 확인 ($AWS_REGION)"
    echo "  - 키 이름 중복 확인"
    echo ""
    exit 1
fi

