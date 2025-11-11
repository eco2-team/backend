# Atlantis Pod CrashLoopBackOff 문제

## 📋 증상

Atlantis Pod가 `CrashLoopBackOff` 상태로 계속 재시작됨

```
NAME         READY   STATUS             RESTARTS   AGE
atlantis-0   0/1     CrashLoopBackOff   15         54m
```

### 에러 메시지

1. **포트 파싱 에러:**
```
Error: 1 error(s) decoding:
* cannot parse 'port' as int: strconv.ParseInt: parsing "tcp://10.97.3.207:80": invalid syntax
```

2. **권한 문제:**
```
Error: initializing server: unable to create dir "/atlantis-data/bin": mkdir /atlantis-data/bin: permission denied
```

---

## 🔍 원인 분석

### 1. 포트 파싱 에러
- Atlantis가 환경 변수나 설정에서 포트를 파싱할 때 Service의 ClusterIP 형식(`tcp://10.97.3.207:80`)을 포트로 인식하려고 시도
- 포트가 명시적으로 설정되지 않아 기본값이나 잘못된 값 사용

### 2. 권한 문제
- PersistentVolume에 대한 쓰기 권한 없음
- `fsGroup`, `runAsUser`, `runAsGroup` 설정 누락

---

## ✅ 해결 방법

### 1. 포트 명시적 설정

`k8s/atlantis/atlantis-deployment.yaml`에서 포트를 명시적으로 설정:

```yaml
args:
  - server
  - --atlantis-url=https://atlantis.growbin.app
  - --repo-allowlist=github.com/SeSACTHON/*
  - --gh-user=SeSACTHON
  - --hide-prev-plan-comments
  - --port=4141  # 포트 명시적 설정
```

### 2. SecurityContext 추가

`k8s/atlantis/atlantis-deployment.yaml`의 `spec.template.spec`에 SecurityContext 추가:

```yaml
spec:
  template:
    spec:
      securityContext:
        fsGroup: 1000
        runAsUser: 1000
        runAsGroup: 1000
      # ... 나머지 설정
```

---

## 🔧 적용된 수정사항

### 1. `k8s/atlantis/atlantis-deployment.yaml`
- ✅ `--port=4141` 명시적 설정 추가
- ✅ `securityContext` 추가 (fsGroup, runAsUser, runAsGroup: 1000)

### 2. `ansible/playbooks/09-atlantis.yml`
- ✅ Service를 NodePort로 자동 변경 로직 추가
- ✅ Ingress 확인 로직 추가

### 3. `ansible/playbooks/07-ingress-resources.yml`
- ✅ 14-nodes-ingress.yaml에 ACM 인증서 ARN 동적 주입

### 4. `ansible/playbooks/09-route53-update.yml`
- ✅ `atlantis.growbin.app` Route53 레코드 자동 생성 추가

---

## 📝 다음 배포 시 자동 적용

다음 배포 시 Ansible playbook이 자동으로:
1. SecurityContext가 포함된 StatefulSet 적용
2. 포트 명시적 설정 적용
3. Service를 NodePort로 변경
4. Ingress 자동 생성 (ACM 인증서 ARN 동적 주입)
5. Route53 레코드 자동 생성

---

## 🔗 관련 문서

- [Atlantis 배포 가이드](../../deployment/ATLANTIS_SETUP_GUIDE.md)
- [Ingress 설정 가이드](../../deployment/ingress-monitoring-verification.md)

---

**작성일**: 2025-11-09  
**해결 버전**: v0.7.0 (14-Node Architecture)

