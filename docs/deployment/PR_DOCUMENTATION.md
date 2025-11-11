# PR: Atlantis Pod CrashLoopBackOff 문제 해결

## 📋 개요

Atlantis Pod가 `CrashLoopBackOff` 상태로 계속 재시작되는 문제를 해결했습니다.

## 🔍 문제 분석

### 증상
- Atlantis Pod가 `CrashLoopBackOff` 상태
- 포트 파싱 에러: `cannot parse 'port' as int`
- 권한 문제: `permission denied: unable to create dir /atlantis-data/bin`

### 원인
1. **포트 파싱 에러**: Atlantis가 환경 변수에서 포트를 파싱할 때 Service의 ClusterIP 형식(`tcp://10.97.3.207:80`)을 포트로 인식
2. **권한 문제**: PersistentVolume에 대한 쓰기 권한 없음 (`fsGroup`, `runAsUser` 설정 누락)

## ✅ 해결 방법

### 1. SecurityContext 추가
`k8s/atlantis/atlantis-deployment.yaml`에 SecurityContext 추가:
```yaml
securityContext:
  fsGroup: 1000
  runAsUser: 1000
  runAsGroup: 1000
```

### 2. 포트 명시적 설정
`--port=4141` 명시적 설정:
```yaml
args:
  - server
  - --port=4141  # 포트 명시적 설정
```

### 3. Ansible 자동화
- Service를 NodePort로 자동 변경
- Route53 레코드 자동 생성
- ACM 인증서 ARN 동적 주입

## 📝 변경된 파일

### Infrastructure 브랜치
- `k8s/atlantis/atlantis-deployment.yaml`: SecurityContext 및 포트 설정 추가
- `ansible/playbooks/09-atlantis.yml`: Service NodePort 변경 로직 추가
- `ansible/playbooks/07-ingress-resources.yml`: ACM 인증서 ARN 동적 주입
- `ansible/playbooks/09-route53-update.yml`: Route53 레코드 자동 생성

### Documentation 브랜치
- `docs/troubleshooting/ATLANTIS_POD_CRASHLOOPBACKOFF.md`: 상세 문제 해결 가이드
- `docs/TROUBLESHOOTING.md`: 인덱스 업데이트

## 🧪 테스트

- [x] Atlantis Pod 정상 실행 확인
- [x] Service NodePort 타입 확인
- [x] Route53 레코드 생성 확인
- [x] Ingress 정상 동작 확인
- [x] https://atlantis.growbin.app 접속 확인

## 🚀 배포 영향

다음 배포 시 Ansible playbook이 자동으로:
1. SecurityContext가 포함된 StatefulSet 적용
2. 포트 명시적 설정 적용
3. Service를 NodePort로 변경
4. Ingress 자동 생성 (ACM 인증서 ARN 동적 주입)
5. Route53 레코드 자동 생성

## 📚 관련 문서

- [Atlantis Pod CrashLoopBackOff 문제 해결 가이드](../troubleshooting/ATLANTIS_POD_CRASHLOOPBACKOFF.md)
- [Atlantis 배포 가이드](ATLANTIS_SETUP_GUIDE.md)

---

**작성일**: 2025-11-09  
**버전**: v0.7.0

