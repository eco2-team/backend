# RabbitMQ 배포 방식 평가

## 현재 구현 평가

### ✅ 올바른 부분

1. **RabbitMQ Cluster Operator 사용**
   - `kubectl apply`로 공식 Operator 설치
   - CRD 자동 설치 포함
   - Operator가 Day-2 운영 관리 (확장, 업그레이드, 롤링 재시작 등)

2. **RabbitmqCluster CR 사용**
   - `RabbitmqCluster` Custom Resource로 브로커 선언
   - Operator가 클러스터링, 상태 관리 자동화
   - 공식 권장 방식 준수

### ⚠️ 문제점

1. **Helm annotation 추가 (불필요)**
   - Operator가 관리하는 리소스에 Helm metadata 추가
   - 관리 혼선 야기 가능
   - Operator와 Helm의 이중 관리 시스템 혼재

2. **Helm Release Secret 생성**
   - `sh.helm.release.v1.rabbitmq.v1` Secret 생성
   - 실제 Helm Chart가 아닌 리소스를 Helm으로 표시
   - `helm list`에 표시되지만 실제 Helm 배포 아님

3. **혼합 방식의 단점**
   - Operator가 충분히 관리 가능한데 Helm 추가
   - 업그레이드/삭제 시 어느 방식으로 해야 할지 혼란
   - 공식 권장 방식에서 벗어남

## 공식 권장 사항

### RabbitMQ 공식 가이드
- **DIY (직접 매니페스트) 배포: 강하게 비권장**
- **Cluster Operator (매우 권장)**
- **신뢰 가능한 Helm Chart (대안)**

### 현재 구현과의 비교

| 항목 | 공식 권장 | 현재 구현 | 평가 |
|------|----------|----------|------|
| Operator 설치 | kubectl apply | kubectl apply | ✅ |
| RabbitmqCluster CR | kubectl apply | kubectl apply | ✅ |
| Helm Chart 사용 | 비권장 (Day-2 이슈) | 사용 안 함 | ✅ |
| Helm annotation | 불필요 | 추가됨 | ⚠️ |

## 권장 개선사항

### 1. Helm annotation 제거
```yaml
# 제거할 부분
metadata:
  labels:
    app.kubernetes.io/managed-by: Helm  # 제거
  annotations:
    meta.helm.sh/release-name: rabbitmq  # 제거
    meta.helm.sh/release-namespace: messaging  # 제거
```

### 2. Helm Release Secret 제거
- `sh.helm.release.v1.rabbitmq.v1` Secret 생성 제거
- Operator가 관리하는 리소스는 Operator 방식 유지

### 3. 순수 Operator 방식 유지
```yaml
# 깔끔한 RabbitmqCluster CR
apiVersion: rabbitmq.com/v1beta1
kind: RabbitmqCluster
metadata:
  name: rabbitmq
  namespace: messaging
  # Helm annotation 없음 (Operator가 관리)
spec:
  replicas: 1
  # ... 나머지 설정
```

## 삭제 프로세스 수정

### 현재 (destroy-with-cleanup.sh)
```bash
# Helm uninstall 먼저 시도
helm uninstall rabbitmq -n messaging
# 그 다음 CR 삭제
kubectl delete rabbitmqcluster rabbitmq -n messaging
```

### 권장 (순수 Operator)
```bash
# RabbitmqCluster CR만 삭제 (Operator가 자동 처리)
kubectl delete rabbitmqcluster rabbitmq -n messaging
# CRD는 유지 (Operator는 유지)
```

## 결론

### 현재 방식 평가: **부분적으로 올바름** ✅⚠️

**올바른 부분:**
- ✅ Operator 사용 (공식 권장)
- ✅ RabbitmqCluster CR 사용 (공식 권장)
- ✅ Day-2 운영 자동화 (Operator 담당)

**개선 필요:**
- ⚠️ Helm annotation 제거
- ⚠️ Helm Release Secret 제거
- ⚠️ 순수 Operator 방식으로 정리

### 최종 권장사항

**"CRD + Helm 배포 유지"** 요구사항 재검토:
- Operator 방식이면 Operator만 사용하는 것이 표준
- Helm은 Operator 설치용으로만 사용 (현재는 kubectl apply 사용 중)
- RabbitmqCluster CR은 kubectl apply로 관리

**개선 방향:**
1. Helm annotation 제거
2. Helm Release Secret 제거
3. 순수 Operator + kubectl apply 방식 유지
4. `kubectl get rabbitmqcluster`로 관리
5. 삭제도 `kubectl delete rabbitmqcluster`로 통일

## 참고

- [RabbitMQ Cluster Operator 공식 문서](https://www.rabbitmq.com/kubernetes/operator/operator-overview.html)
- RabbitMQ는 Operator 중심 운영을 강력 권장
- Helm은 설치 도구로만 사용, 운영은 Operator에 맡김
