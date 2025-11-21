# PostgreSQL Secret 설정 검증

## ✅ SSM → External Secret → PostgreSQL 연결 확인

### 1. AWS SSM Parameter
```
/sesacthon/dev/data/postgres-password
```
- Terraform이 자동으로 생성한 랜덤 비밀번호
- 32자 길이

---

### 2. External Secret (data-secrets.yaml)

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: postgresql-credentials
  namespace: postgres  # ✅ postgres namespace
spec:
  refreshInterval: 1h
  secretStoreRef:
    kind: ClusterSecretStore
    name: aws-ssm-store
  data:
    - secretKey: dbPassword
      remoteRef:
        key: /sesacthon/dev/data/postgres-password  # ← SSM에서 가져옴
  target:
    name: postgresql-secret  # ✅ 생성될 Secret 이름
    creationPolicy: Owner
    template:
      type: Opaque
      data:
        username: postgres
        password: "{{ .dbPassword }}"           # ✅ 일반 사용자 비밀번호
        postgres-password: "{{ .dbPassword }}"  # ✅ superuser 비밀번호
```

**생성되는 Secret:**
- Secret 이름: `postgresql-secret`
- Namespace: `postgres`
- 키:
  - `username`: postgres
  - `password`: SSM에서 가져온 비밀번호
  - `postgres-password`: SSM에서 가져온 비밀번호 (동일)

---

### 3. PostgreSQL Helm Chart (27-postgresql.yaml)

```yaml
auth:
  existingSecret: postgresql-secret  # ✅ 위에서 생성된 Secret 참조
  secretKeys:
    adminPasswordKey: postgres-password  # ✅ superuser 비밀번호 키
    userPasswordKey: password            # ✅ 일반 사용자 비밀번호 키
  username: sesacthon  # ✅ 생성할 사용자 이름
  database: ecoeco     # ✅ 생성할 데이터베이스 이름
```

**의미:**
- PostgreSQL Chart가 `postgresql-secret`에서 비밀번호를 읽음
- `postgres` superuser: `postgres-password` 키 사용
- `sesacthon` 일반 사용자: `password` 키 사용 (같은 비밀번호)

---

## ✅ 연결 흐름

```
AWS SSM Parameter Store
  /sesacthon/dev/data/postgres-password: "랜덤32자비밀번호"
         ↓
External Secrets Operator (자동 동기화)
         ↓
Kubernetes Secret (postgres namespace)
  name: postgresql-secret
  data:
    username: postgres
    password: "랜덤32자비밀번호"
    postgres-password: "랜덤32자비밀번호"
         ↓
PostgreSQL Helm Chart
  - postgres superuser: postgres-password 키 사용
  - sesacthon 사용자: password 키 사용
  - 데이터베이스: ecoeco 생성
  - 스키마: auth 생성 (initdb)
```

---

## ✅ 검증 명령어

### 1. SSM Parameter 확인
```bash
aws ssm get-parameter \
    --name /sesacthon/dev/data/postgres-password \
    --with-decryption \
    --query 'Parameter.Value' \
    --output text
```

### 2. External Secret 동작 확인
```bash
# External Secret 상태
kubectl -n postgres get externalsecret postgresql-credentials

# 생성된 Secret 확인
kubectl -n postgres get secret postgresql-secret

# Secret 내용 확인 (base64 디코드)
kubectl -n postgres get secret postgresql-secret -o yaml
```

### 3. Secret 키 확인
```bash
# username 확인
kubectl -n postgres get secret postgresql-secret \
    -o jsonpath='{.data.username}' | base64 -d

# password 확인 (처음 10자만)
kubectl -n postgres get secret postgresql-secret \
    -o jsonpath='{.data.password}' | base64 -d | cut -c1-10

# postgres-password 확인 (처음 10자만)
kubectl -n postgres get secret postgresql-secret \
    -o jsonpath='{.data.postgres-password}' | base64 -d | cut -c1-10
```

### 4. PostgreSQL 접속 테스트
```bash
# sesacthon 사용자로 접속
kubectl -n postgres exec -it dev-postgresql-0 -- \
    psql -U sesacthon -d ecoeco -c "SELECT current_user, current_database();"

# 예상 출력:
#  current_user | current_database
# --------------+------------------
#  sesacthon    | ecoeco
```

---

## ✅ 완벽하게 설정됨!

**모든 연결이 올바르게 구성되었습니다:**

1. ✅ SSM에서 비밀번호 가져오기
2. ✅ External Secret이 `postgresql-secret` 생성
3. ✅ 올바른 키 이름 사용 (`postgres-password`, `password`)
4. ✅ PostgreSQL Chart가 Secret 참조
5. ✅ `sesacthon` 사용자, `ecoeco` 데이터베이스 생성
6. ✅ `auth` 스키마 자동 생성 (initdb)

**추가 작업 불필요!** 이미 완벽하게 구성되어 있습니다. 🎉

---

## 🔧 트러블슈팅

### Secret이 생성 안 됨
```bash
# External Secrets Operator 확인
kubectl -n external-secrets get pods

# External Secret 로그
kubectl -n postgres describe externalsecret postgresql-credentials
```

### 비밀번호 인증 실패
```bash
# Secret 값과 PostgreSQL 설정 비교
kubectl -n postgres get secret postgresql-secret -o yaml
kubectl -n postgres exec -it dev-postgresql-0 -- env | grep POSTGRES
```

---

## 📝 요약

**현재 설정은 완벽합니다!** ✅

- External Secret: `postgresql-secret` (postgres namespace)
- 키: `postgres-password`, `password`, `username`
- Chart 참조: `existingSecret: postgresql-secret`
- 키 매핑: `adminPasswordKey: postgres-password`, `userPasswordKey: password`

**SSM → External Secret → PostgreSQL 완벽 연결!** 🎊

