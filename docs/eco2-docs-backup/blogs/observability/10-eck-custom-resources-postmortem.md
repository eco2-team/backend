# eck-custom-resources 도입 실패 포스트모템

> **작업 기간**: 2025-12-18 01:11 ~ 03:07 (약 2시간)
> **결론**: 도입 실패 → 폐기

## 📋 요약

Kibana 대시보드를 Kubernetes CRD로 선언적 관리하기 위해 `eck-custom-resources` 오픈소스 operator를 도입했으나, 지속적인 호환성 문제와 프로젝트 유지보수 중단으로 폐기 결정.

---

## 🎯 목표

- Kibana 대시보드를 Git으로 버전 관리
- ArgoCD GitOps와 통합하여 선언적 배포
- Dashboard, DataView를 Kubernetes CR로 정의

---

## 🔧 사용한 도구

| 도구 | 버전 | 링크 |
|------|------|------|
| eck-custom-resources | v0.7.0 | https://github.com/xco-sk/eck-custom-resources |
| ECK Operator | 2.9+ | https://github.com/elastic/cloud-on-k8s |
| Kibana | 8.11.0 | - |

---

## ⏱️ 타임라인 (커밋 기준)

| 시간 | 커밋 | 작업 내용 | 결과 |
|------|------|----------|------|
| 01:11 | `791dfced` | 초기 도입 - Dashboard, DataView CR 정의 | ❌ CR 생성 안됨 |
| 01:31 | `dfd724c0` | CRD 스키마 수정 | ❌ KibanaInstance not found |
| 01:50 | `928769e9` | eck-custom-resources operator 추가 | ❌ operator 배포 실패 |
| 02:03 | `80a2cab7` | KibanaInstance 설정 추가 | ❌ enabled 필드 누락 |
| 02:15 | `255acff7` | `spec.enabled: true` 추가 | ❌ certificate 에러 |
| 02:19 | `931dc7f7` | certificate 설정 추가 | ❌ HTTPS/HTTP 불일치 |
| 02:29 | `ca54838d` | NetworkPolicy 수정 (elastic-system → logging) | ❌ connection timeout |
| 02:31 | `a887ea38` | HTTP URL로 변경 | ✅ operator 연결 성공 |
| 02:34 | `3b7b5d5c` | DataView body 형식 수정 | ❌ title undefined |
| 02:36 | `5d488423` | 인덱스 패턴 logs-* 수정 | ❌ data_view wrapper 문제 |
| 02:41 | `0163c6c1` | data_view wrapper 제거 | ✅ DataView 생성 성공 |
| 02:48 | `39115431` | searchSourceJSON 추가 | ❌ searchSource 에러 |
| 02:52 | `2741c0e5` | 패널별 references 추가 | ❌ 여전히 에러 |
| 03:01 | `0b62f1f8` | indexRefName 추가 | ❌ 여전히 에러 |
| 03:07 | `ec910d75` | indexRefName 제거 (정상 대시보드 참고) | ❌ **여전히 에러** |

**총 소요 시간: 약 2시간**
**커밋 횟수: 16회**
**성공률: 0% (대시보드 렌더링 실패)**

---

## 🐛 발생한 에러들

### 1. KibanaInstance not found
```
KibanaInstance.kibana.eck.github.com "eco2-kibana" not found
```
**원인**: ArgoCD sync-wave 순서 문제
**해결**: sync-wave 조정

### 2. Required field 'enabled'
```
KibanaInstance.kibana.eck.github.com "eco2-kibana" is invalid: spec.enabled: Required value
```
**원인**: CRD 스키마에 필수 필드 누락
**해결**: `spec.enabled: true` 추가

### 3. Certificate not configured
```
Failed to configure http client, certificate not configured (kibana.certificate)
```
**원인**: HTTPS 연결 시 인증서 미설정
**해결**: `spec.certificate` 추가

### 4. HTTP response to HTTPS client
```
http: server gave HTTP response to HTTPS client
```
**원인**: ECK Kibana가 TLS disabled 상태
**해결**: URL을 `http://`로 변경

### 5. Connection timeout
```
dial tcp ...: connect: connection timed out
```
**원인**: NetworkPolicy가 elastic-system → logging 차단
**해결**: NetworkPolicy 수정

### 6. DataView title undefined
```
[request body.data_view.title]: expected value of type [string] but got [undefined]
```
**원인**: DataView CR body 형식이 Kibana API와 불일치
**해결**: `data_view` wrapper 제거

### 7. Cannot read 'searchSource' (최종 미해결)
```
Cannot read properties of undefined (reading 'searchSource')
```
**원인**: Lens 패널의 references 구조가 Kibana 8.x와 호환되지 않음
**시도한 해결책**:
- `kibanaSavedObjectMeta.searchSourceJSON` 추가
- top-level `references` 배열에 패널별 참조 추가
- `indexRefName` 추가/제거

**결과**: 모든 시도 실패

---

## 🔍 근본 원인 분석

### 1. 프로젝트 유지보수 중단
- **마지막 릴리즈**: 2024년 2월 5일 (v0.7.0)
- **약 10개월간 업데이트 없음**
- Kibana 8.x의 Dashboard JSON 구조 변경에 대응 안됨

### 2. Kibana Saved Objects API 변경
- Kibana 8.7+에서 대부분의 Saved Objects API deprecated
- Import/Export API만 지원
- eck-custom-resources는 구버전 API 사용

### 3. Lens 시각화 복잡성
- Lens 패널은 by-value로 저장 시 복잡한 references 구조 필요
- 정확한 JSON 구조가 문서화되어 있지 않음
- Kibana UI에서 생성한 대시보드와 구조가 미묘하게 다름

---

## ✅ 대안

### 1. Kibana Import API + Job (권장)
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: import-kibana-dashboards
spec:
  template:
    spec:
      containers:
      - name: import
        image: curlimages/curl
        command: ["sh", "-c", "curl -X POST kibana:5601/api/saved_objects/_import ..."]
```

### 2. Elastic Terraform Provider
```hcl
resource "elasticstack_kibana_import_saved_objects" "dashboards" {
  file_contents = file("dashboards.ndjson")
}
```

### 3. Kibana UI + Export → Git
1. Kibana UI에서 대시보드 생성
2. Export → ndjson
3. Git 저장
4. CI/CD에서 Import

---

## 📝 교훈

1. **오픈소스 도입 전 유지보수 상태 확인 필수**
   - 마지막 커밋/릴리즈 날짜
   - 이슈 응답 속도
   - 커뮤니티 활성도

2. **복잡한 JSON 구조는 UI에서 생성 후 Export가 안전**
   - Kibana Dashboard JSON은 버전별로 미묘하게 다름
   - 수동 작성 시 디버깅이 매우 어려움

3. **공식 도구 우선 검토**
   - Elastic 공식 Terraform Provider 존재
   - 커뮤니티 프로젝트보다 안정적

---

## 🗑️ 정리 작업

폐기된 파일들:
- `workloads/kibana/base/` (Dashboard, DataView, KibanaInstance CR)
- `clusters/dev/apps/64-eck-custom-resources-operator.yaml`
- `clusters/dev/apps/65-eck-custom-resources-cr.yaml`

---

## 📚 참고 자료

- [eck-custom-resources GitHub](https://github.com/xco-sk/eck-custom-resources)
- [Kibana Saved Objects API (Deprecated)](https://www.elastic.co/guide/en/kibana/current/saved-objects-api.html)
- [Elastic Terraform Provider](https://github.com/elastic/terraform-provider-elasticstack)
- [Kibana Import/Export API](https://www.elastic.co/guide/en/kibana/current/saved-objects-api-import.html)

