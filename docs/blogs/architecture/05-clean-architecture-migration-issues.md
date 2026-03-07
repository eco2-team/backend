# Clean Architecture 마이그레이션 유의사항

> Auth/Users 도메인을 Clean Architecture로 리팩토링하면서 발생한 이슈들을 정리합니다.
> 다른 도메인 마이그레이션 시 참고하세요.

---

## 1. domains와의 정합성 문제

### 1.1 응답 형식 불일치

**문제**: Clean Architecture 버전이 다른 응답 형식을 반환하면 프론트엔드 동작 안함

| 엔드포인트 | domains | apps (잘못된 예) | apps (올바른 예) |
|---|---|---|---|
| `POST /logout` | `{"success": true, "data": {...}}` | `{"message": "..."}` | `LogoutSuccessResponse` 사용 |
| `POST /refresh` | body 없음, 201 | `TokenResponse` 반환 | `return None` |

**해결**: domains의 응답 스키마를 그대로 복사하거나, 정확히 일치하는지 확인

---

### 1.2 토큰 읽기 방식

**문제**: EnvoyFilter가 쿠키를 헤더로 변환하므로, 직접 쿠키에서 읽으면 안됨

```python
# ❌ 잘못된 방식 (쿠키에서 직접 읽기)
access_token: str = Cookie(None, alias="s_access")

# ✅ 올바른 방식 (헤더에서 읽기)
authorization: str = Header(None, alias="Authorization")
access_token = _parse_bearer(authorization)
```

**적용 대상**: logout, refresh 등 토큰이 필요한 모든 엔드포인트

---

### 1.3 쿠키 설정

**문제**: 쿠키 이름, 도메인이 기존과 다르면 프론트엔드에서 인식 못함

| 항목 | domains | 일치 필요 |
|---|---|---|
| Access 쿠키 이름 | `s_access` | ✅ |
| Refresh 쿠키 이름 | `s_refresh` | ✅ |
| 도메인 환경변수 | `AUTH_COOKIE_DOMAIN` | ✅ |

**주의**: `RedirectResponse`에 쿠키를 설정해야 함 (일반 `Response`에 설정하면 전달 안됨)

```python
# ❌ 잘못된 방식
response = Response()
set_auth_cookies(response, ...)
return RedirectResponse(url=...)  # 쿠키 누락!

# ✅ 올바른 방식
redirect_response = RedirectResponse(url=...)
set_auth_cookies(redirect_response, ...)
return redirect_response
```

---

### 1.4 스키마 필드명

**문제**: 필드명이 다르면 프론트엔드 파싱 실패

| domains/my | apps/users (잘못된 예) | apps/users (올바른 예) |
|---|---|---|
| `code` | `character_code` | `code` |
| `name` | `character_name` | `name` |
| `character_name` (path) | `character_code` | `character_name` |

**원칙**: domains의 스키마를 먼저 확인하고 동일하게 맞출 것

---

### 1.5 라우트 경로 충돌

**문제**: `/{provider}` 같은 동적 경로가 `/docs`, `/openapi.json` 등과 충돌

```python
# ❌ 모든 문자열 매칭
@router.get("/{provider}")
async def authorize(provider: str): ...

# ✅ Enum으로 제한
class OAuthProviderPath(str, Enum):
    google = "google"
    kakao = "kakao"
    naver = "naver"

@router.get("/{provider}")
async def authorize(provider: OAuthProviderPath): ...
```

---

## 2. 인프라/라이브러리 문제

### 2.1 Protobuf 버전 충돌

**문제**: `opentelemetry-proto`가 protobuf 5.x 요구, 생성된 코드는 6.x

**해결**: 생성된 `_pb2.py` 파일에서 버전 체크 비활성화

```python
# 주석 처리
# _runtime_version.ValidateProtobufRuntimeVersion(...)
```

---

### 2.2 SQLAlchemy + Dataclass 호환

**문제 1**: `frozen=True` dataclass는 SQLAlchemy가 `_sa_instance_state` 설정 불가

```python
# ❌
@dataclass(frozen=True)
class LoginAudit: ...

# ✅
@dataclass
class LoginAudit: ...
```

**문제 2**: `__slots__` 사용 시 `__weakref__` 필요

```python
class User(Entity):
    __slots__ = (
        "username",
        # ...
        "__weakref__",  # 필수!
    )
```

---

### 2.3 ENUM 값 매핑

**문제**: Python Enum 이름(대문자)이 DB에 들어감, DB는 소문자 기대

```python
# ❌ DB에 "KAKAO" 저장됨
Column("provider", Enum(OAuthProvider))

# ✅ DB에 "kakao" 저장됨
Column(
    "provider",
    Enum(OAuthProvider, values_callable=lambda x: [e.value for e in x])
)
```

---

### 2.4 gRPC Import 경로

**문제**: 생성된 `_pb2_grpc.py`가 상대 import 사용

```python
# ❌ 생성된 코드 (동작 안함)
import users_pb2 as users__pb2

# ✅ 수정 필요
from apps.auth.infrastructure.grpc import users_pb2 as users__pb2
```

---

### 2.5 NetworkPolicy / DestinationRule

**문제**: 서비스 간 gRPC 통신 시 NetworkPolicy, Istio DestinationRule 필요

```yaml
# NetworkPolicy: auth → users-api-grpc 허용
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-auth-to-users-grpc
  namespace: auth
spec:
  podSelector: {}
  policyTypes: [Egress]
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: users
          podSelector:
            matchLabels:
              app: users-api-grpc
      ports:
        - protocol: TCP
          port: 50051
```

---

## 3. CI/CD 관련

### 3.1 Squash Merge 시 파일 누락

**문제**: PR squash merge 시 일부 파일 변경사항이 누락될 수 있음

**확인 방법**:
```bash
git show <commit_hash> -- <file_path>
# 출력이 비어있으면 해당 파일이 커밋에 포함되지 않은 것
```

**해결**: develop 브랜치에서 직접 수정 후 push

---

## 4. 체크리스트

새 도메인 마이그레이션 시 확인:

- [ ] 응답 스키마가 domains와 동일한가?
- [ ] 토큰을 헤더에서 읽는가? (쿠키 X)
- [ ] 쿠키 이름이 `s_access`, `s_refresh`인가?
- [ ] RedirectResponse에 쿠키를 설정하는가?
- [ ] Enum 값이 소문자로 DB에 저장되는가?
- [ ] `/{param}` 경로가 `/docs` 등과 충돌하지 않는가?
- [ ] gRPC 사용 시 NetworkPolicy 설정했는가?
- [ ] dataclass에 `frozen=True` 사용하지 않았는가?
- [ ] `__slots__` 사용 시 `__weakref__` 포함했는가?

---

## 5. 마이그레이션 절차

### 5.1 스키마 마이그레이션

#### 1단계: 마이그레이션 스크립트 작성

```sql
-- migrations/V003__create_users_schema.sql
SET timezone = 'Asia/Seoul';

-- 1. ENUM 타입 정의
CREATE TYPE users.oauth_provider AS ENUM ('google', 'kakao', 'naver');
CREATE TYPE users.user_character_status AS ENUM ('active', 'inactive');

-- 2. 테이블 생성
CREATE TABLE users.accounts (
    id UUID PRIMARY KEY,
    nickname TEXT,
    -- ...
);

-- 3. 데이터 이전 (중복 처리 포함)
INSERT INTO users.accounts (id, nickname, ...)
SELECT DISTINCT ON (phone_number) 
    id, nickname, ...
FROM auth.users
ORDER BY phone_number, last_login_at DESC NULLS LAST;
```

#### 2단계: 마이그레이션 실행

```bash
# Storage 노드에서 실행
./scripts/utilities/connect-ssh.sh storage

# PostgreSQL 접속
kubectl port-forward -n postgres svc/dev-postgresql 5432:5432 &
psql -h localhost -U postgres -d ecoeco

# 스크립트 실행
\i /path/to/V003__create_users_schema.sql

# 검증
SELECT COUNT(*) FROM users.accounts;
SELECT COUNT(*) FROM users.social_accounts;
```

---

### 5.2 Kubernetes 노드 추가 (Terraform + Ansible)

#### 1단계: Terraform으로 EC2 인스턴스 생성

```hcl
# terraform/main.tf
module "api_users" {
  source = "./modules/ec2_node"
  
  name          = "k8s-api-users"
  instance_type = "t3.medium"
  
  k8s_labels = {
    domain = "users"
  }
  k8s_taints = "domain=users:NoSchedule"
}
```

```bash
cd terraform
terraform plan
terraform apply
```

#### 2단계: Ansible inventory 업데이트

```ini
# ansible/inventory/hosts.ini
[api_nodes]
k8s-api-users ansible_host=<PUBLIC_IP> private_ip=<PRIVATE_IP>

[new_workers]
k8s-api-users
```

#### 3단계: 노드 클러스터 조인

```bash
cd ansible
ansible-playbook -i inventory/hosts.ini playbooks/join-workers.yml
```

---

### 5.3 gRPC 서비스 설정

#### 1단계: Protobuf 정의 및 코드 생성

```bash
# apps/users/presentation/grpc/protos/
python -m grpc_tools.protoc \
  -I. \
  --python_out=. \
  --grpc_python_out=. \
  users.proto
```

#### 2단계: 생성된 코드 수정

```python
# users_pb2.py - 버전 체크 비활성화
# _runtime_version.ValidateProtobufRuntimeVersion(...)

# users_pb2_grpc.py - 임포트 경로 수정
from apps.users.presentation.grpc.protos import users_pb2 as users__pb2
```

#### 3단계: Kubernetes 리소스 배포

```yaml
# workloads/domains/users/base/
- deployment-grpc.yaml     # gRPC 서버 Deployment
- service-grpc.yaml        # ClusterIP Service (50051)
- destination-rule-grpc.yaml  # Istio DestinationRule
```

```yaml
# workloads/network-policies/base/
- allow-auth-to-users-grpc.yaml  # auth → users gRPC 허용
```

---

### 5.4 Canary 배포 테스트

#### 1단계: Canary 버전 배포

```yaml
# workloads/domains/auth/base/deployment-canary.yaml
metadata:
  labels:
    version: canary
spec:
  replicas: 1
```

#### 2단계: VirtualService 설정

```yaml
# workloads/routing/gateway/base/virtual-service.yaml
http:
  - match:
      - headers:
          x-canary:
            exact: "true"
    route:
      - destination:
          host: auth-api.auth.svc.cluster.local
          subset: canary
  - route:
      - destination:
          subset: stable
```

#### 3단계: 테스트

```bash
# Canary 테스트
curl -H "x-canary: true" https://api.example.com/api/v1/auth/health

# Stable 테스트
curl https://api.example.com/api/v1/auth/health
```

---

### 5.5 AuthorizationPolicy 업데이트

인증이 필요 없는 경로는 ext-authz 바이패스:

```yaml
# workloads/routing/gateway/base/authorization-policy.yaml
spec:
  rules:
    - to:
        - operation:
            notPaths:
              # OAuth 콜백 (인증 전)
              - /api/v1/auth/*/callback*
              # 로그인 URL 요청
              - /api/v1/auth/kakao*
              - /api/v1/auth/google*
              - /api/v1/auth/naver*
              # API 문서
              - /api/v1/*/docs
              - /api/v1/*/openapi.json
```

---

## 6. 마이그레이션 순서 권장

```
1. [코드] apps/ 디렉토리에 Clean Architecture 코드 작성
2. [DB] 스키마 마이그레이션 스크립트 작성 및 테스트
3. [K8s] Canary Deployment 작성
4. [배포] Canary 배포 (x-canary 헤더로 테스트)
5. [검증] domains 대비 응답 형식 일치 확인
6. [DB] 프로덕션 스키마 마이그레이션 실행
7. [배포] Stable 배포로 전환
8. [정리] 기존 domains 코드 제거 (선택적)
```

