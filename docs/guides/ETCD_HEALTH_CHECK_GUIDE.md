# etcd 상태 확인 가이드

## etcd 상태 확인 경고 발생 시

`check-cluster-health.sh`에서 "⚠️ etcd: 상태 확인 불가 또는 비정상" 경고가 나올 때 클러스터에서 직접 점검하는 방법입니다.

---

## 빠른 확인 방법

### 1. 전용 스크립트 사용 (권장)

```bash
./scripts/check-etcd-health.sh
```

이 스크립트는 자동으로:
- etcd 인증서 경로 찾기
- etcdctl 설치 확인
- etcd health check 실행
- 문제 진단 및 해결 방법 제시

---

## Master 노드에서 직접 확인

### 2. SSH 접속

```bash
# Master 노드 접속
./scripts/connect-ssh.sh master

# 또는 직접 접속
ssh -i ~/.ssh/sesacthon ubuntu@<MASTER_IP>
```

### 3. etcd 인증서 경로 확인

```bash
# kubeadm 기본 경로 확인
ls -la /etc/kubernetes/pki/etcd/

# 필요한 파일:
# - ca.crt
# - server.crt
# - server.key
```

### 4. etcdctl 설치 확인

```bash
which etcdctl

# 없으면 설치:
sudo apt-get update
sudo apt-get install -y etcd-client

# 또는 직접 다운로드:
ETCD_VER=v3.5.9
curl -L https://github.com/etcd-io/etcd/releases/download/${ETCD_VER}/etcd-${ETCD_VER}-linux-amd64.tar.gz -o /tmp/etcd.tar.gz
tar xzvf /tmp/etcd.tar.gz -C /tmp
sudo mv /tmp/etcd-${ETCD_VER}-linux-amd64/etcdctl /usr/local/bin/
```

### 5. etcd Health Check 실행

#### 방법 1: kubeadm 기본 경로 (대부분의 경우)

```bash
sudo ETCDCTL_API=3 etcdctl endpoint health \
    --endpoints=https://127.0.0.1:2379 \
    --cacert=/etc/kubernetes/pki/etcd/ca.crt \
    --cert=/etc/kubernetes/pki/etcd/server.crt \
    --key=/etc/kubernetes/pki/etcd/server.key
```

#### 방법 2: 대체 경로 (경우에 따라 다를 수 있음)

```bash
sudo ETCDCTL_API=3 etcdctl endpoint health \
    --endpoints=https://127.0.0.1:2379 \
    --cacert=/etc/etcd/pki/ca.crt \
    --cert=/etc/etcd/pki/apiserver-etcd-client.crt \
    --key=/etc/etcd/pki/apiserver-etcd-client.key
```

### 6. etcd 상태 상세 정보 확인

```bash
# Endpoint status
sudo ETCDCTL_API=3 etcdctl endpoint status \
    --endpoints=https://127.0.0.1:2379 \
    --cacert=/etc/kubernetes/pki/etcd/ca.crt \
    --cert=/etc/kubernetes/pki/etcd/server.crt \
    --key=/etc/kubernetes/pki/etcd/server.key \
    --write-out=table

# Member list
sudo ETCDCTL_API=3 etcdctl member list \
    --endpoints=https://127.0.0.1:2379 \
    --cacert=/etc/kubernetes/pki/etcd/ca.crt \
    --cert=/etc/kubernetes/pki/etcd/server.crt \
    --key=/etc/kubernetes/pki/etcd/server.key \
    --write-out=table
```

---

## 문제 해결

### 문제 1: etcdctl이 없음

```bash
# 설치
sudo apt-get install -y etcd-client

# 또는 바이너리 직접 설치
ETCD_VER=v3.5.9
cd /tmp
wget https://github.com/etcd-io/etcd/releases/download/${ETCD_VER}/etcd-${ETCD_VER}-linux-amd64.tar.gz
tar xzvf etcd-${ETCD_VER}-linux-amd64.tar.gz
sudo mv etcd-${ETCD_VER}-linux-amd64/etcdctl /usr/local/bin/
```

### 문제 2: 인증서 경로를 찾을 수 없음

```bash
# 인증서 파일 검색
sudo find /etc -name "ca.crt" -path "*/etcd/*" 2>/dev/null
sudo find /etc -name "server.crt" -path "*/etcd/*" 2>/dev/null
sudo find /etc -name "server.key" -path "*/etcd/*" 2>/dev/null

# Kubernetes 인증서 전체 목록
ls -la /etc/kubernetes/pki/
```

### 문제 3: etcd가 응답하지 않음

```bash
# etcd 프로세스 확인
sudo ps aux | grep etcd | grep -v grep

# etcd Pod 확인 (static Pod인 경우)
sudo crictl pods | grep etcd

# 또는 kubelet이 관리하는 static Pod 확인
ls -la /etc/kubernetes/manifests/ | grep etcd

# etcd 포트 확인
sudo netstat -tlnp | grep 2379
sudo ss -tlnp | grep 2379

# etcd 로그 확인
sudo journalctl -u etcd -n 50 --no-pager
# 또는
sudo tail -f /var/log/etcd.log
```

### 문제 4: 인증서 권한 오류

```bash
# 인증서 파일 권한 확인
ls -la /etc/kubernetes/pki/etcd/

# 필요시 권한 수정 (주의: 보안 위험)
sudo chmod 644 /etc/kubernetes/pki/etcd/*.crt
sudo chmod 600 /etc/kubernetes/pki/etcd/*.key
```

---

## 체크리스트

### ✅ 정상 상태일 때

```bash
$ sudo ETCDCTL_API=3 etcdctl endpoint health \
    --endpoints=https://127.0.0.1:2379 \
    --cacert=/etc/kubernetes/pki/etcd/ca.crt \
    --cert=/etc/kubernetes/pki/etcd/server.crt \
    --key=/etc/kubernetes/pki/etcd/server.key

https://127.0.0.1:2379 is healthy: successfully committed proposal: took = 2.123456ms
```

### ⚠️ 문제가 있을 때

- `connection refused`: etcd가 실행 중이 아님
- `certificate verify failed`: 인증서 경로 또는 권한 문제
- `context deadline exceeded`: etcd가 응답하지 않음 (성능 이슈 또는 다운)

---

## 참고 사항

1. **인증서 경로**: kubeadm으로 설치한 클러스터는 일반적으로 `/etc/kubernetes/pki/etcd/`를 사용합니다.

2. **etcd 실행 방식**:
   - kubeadm: Master 노드의 static Pod로 실행
   - 외부 etcd: 별도 서버에서 실행

3. **포트**: 기본적으로 `2379` (클라이언트), `2380` (피어 통신)

4. **백업**: etcd 백업은 `/usr/local/bin/backup-etcd.sh`로 설정되어 있습니다.

---

## 빠른 명령어 요약

```bash
# 1. 스크립트로 자동 확인
./scripts/check-etcd-health.sh

# 2. Master 노드 접속
./scripts/connect-ssh.sh master

# 3. 직접 health check
sudo ETCDCTL_API=3 etcdctl endpoint health \
    --endpoints=https://127.0.0.1:2379 \
    --cacert=/etc/kubernetes/pki/etcd/ca.crt \
    --cert=/etc/kubernetes/pki/etcd/server.crt \
    --key=/etc/kubernetes/pki/etcd/server.key
```

