# macOS TLS 인증서 문제 해결 가이드

## 🚨 문제 설명

**증상:**
```
tls: failed to verify certificate: x509: OSStatus -26276
```

**영향:**
- Terraform이 AWS STS에 접근 불가
- Terraform Registry에 접근 불가
- 클러스터 구축 진행 불가

---

## 📋 원인

macOS OSStatus -26276 에러는 다음 중 하나가 원인입니다:

1. **시스템 날짜/시간이 잘못됨**
2. **키체인의 SSL/TLS 루트 인증서가 손상됨**
3. **보안 소프트웨어나 방화벽의 인증서 검사 간섭**

---

## 🛠️ 해결 방법

### 방법 1: 시스템 날짜/시간 확인 및 수정 (가장 흔한 원인)

```bash
# 현재 날짜/시간 확인
date

# 네트워크 시간 동기화 활성화
sudo systemsetup -setusingnetworktime on

# NTP 서버 재동기화
sudo sntp -sS time.apple.com
```

### 방법 2: 시스템 키체인 인증서 재설정

```bash
# 인증서 다운로드 (Amazon Root CA)
curl -o ~/amazon-root-ca.pem https://www.amazontrust.com/repository/AmazonRootCA1.pem

# 시스템 키체인에 추가
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain \
  ~/amazon-root-ca.pem

# Terraform 재시도
cd /Users/mango/workspace/SeSACTHON/backend/terraform
terraform init -upgrade
```

### 방법 3: Terraform 플러그인 미러 사용

```bash
# 플러그인을 로컬에 미리 다운로드
mkdir -p ~/.terraform.d/plugins
terraform providers mirror ~/.terraform.d/plugins

# .terraformrc 설정
cat > ~/.terraformrc <<EOF
provider_installation {
  filesystem_mirror {
    path    = "$HOME/.terraform.d/plugins"
    include = ["hashicorp/*"]
  }
  direct {
    exclude = ["hashicorp/*"]
  }
}
EOF

# Terraform 재시도
cd /Users/mango/workspace/SeSACTHON/backend/terraform
terraform init -upgrade
```

### 방법 4: SSL 검증 임시 비활성화 (권장하지 않음)

```bash
# 환경 변수 설정
export TF_CLI_CONFIG_FILE=""
export AWS_CA_BUNDLE=""
export GODEBUG=x509ignoreCN=0

# Terraform 재시도
cd /Users/mango/workspace/SeSACTHON/backend/terraform
terraform init -upgrade
```

---

## ✅ 해결 확인

다음 명령어로 TLS 연결이 정상 작동하는지 확인:

```bash
# AWS STS 접근 테스트
aws sts get-caller-identity

# Terraform Registry 접근 테스트
curl -I https://registry.terraform.io/.well-known/terraform.json

# Terraform init 재시도
cd /Users/mango/workspace/SeSACTHON/backend/terraform
terraform init -upgrade
```

---

## 🎯 클러스터 구축 재개

문제가 해결되면 다음 명령어로 클러스터 구축을 재개하세요:

```bash
cd /Users/mango/workspace/SeSACTHON/backend/scripts
AUTO_MODE=true ./build-cluster.sh
```

---

## 📚 참고

- [macOS OSStatus Error Codes](https://www.osstatus.com/)
- [Terraform TLS Issues](https://discuss.hashicorp.com/t/terraform-tls-certificate-verification-error/39159)
- [AWS Certificate Bundle](https://docs.aws.amazon.com/sdk-for-go/v1/developer-guide/configuring-sdk.html#using-custom-ca-bundle)

