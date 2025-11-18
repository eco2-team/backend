# Platform stack 이중 Application 제거

## 배경
- `clusters/dev/apps/25-data-operators.yaml` ApplicationSet이 `dev-{{name}}` 패턴으로 상위 Application을 생성하면서 Redis 항목에 대해 `dev-redis-operator`를 만든다.
```1:34:clusters/dev/apps/25-data-operators.yaml
metadata:
  name: dev-{{name}}
```
- `platform/helm/redis-operator` 경로 또한 자체적으로 Argo Application 매니페스트를 내보내고, dev 오버레이에서 `namePrefix: dev-`를 붙여 동일한 `dev-redis-operator` 객체를 다시 생성한다.
```1:7:platform/helm/redis-operator/dev/kustomization.yaml
resources:
  - ../base
namePrefix: dev-
```
- 두 레이어가 같은 이름·네임스페이스의 Application을 동시에 reconcile하면서 ownerReference와 annotations를 계속 덮어써 OutOfSync가 반복되었다.

## 변경 방향
1. **ApplicationSet → Helm 직접 연결**  
   - `clusters/*/apps/25-data-operators.yaml`에서 Redis 항목만 별도 분기해 `source.repoURL`/`chart`/`targetRevision`을 직접 지정하도록 수정한다.  
   - 이때 release 이름과 namespace는 기존 `platform/helm/redis-operator`와 동일하게 유지해 리소스 재생성을 피한다.
2. **platform/helm/redis-operator 제거**  
   - App-of-App 패턴을 없애기 위해 해당 경로의 Application 매니페스트를 삭제하고, 필요 시 README에 ApplicationSet에서 Helm chart를 바로 긁어온다는 사실만 기록한다.
3. **동일 이름 충돌 방지**  
   - 상위 Application 이름은 그대로 `dev-redis-operator`로 두되, 더 이상 하위 Application을 생성하지 않으므로 self-manage 루프가 소멸한다.

## TODO
- [ ] `clusters/dev/apps/25-data-operators.yaml` 및 prod 대응 파일에 Helm source 블록 삽입
- [ ] `platform/helm/redis-operator` 디렉터리 정리
- [ ] Argo에서 `dev-redis-operator` Diff 확인 후 Sync
- [ ] `platform/cr/{base,dev,prod}` README에 선행 조건 문구 업데이트 (Wave 25가 ApplicationSet임을 명시)

## 기대 효과
- 동일 리소스를 중복 관리하던 루프가 사라져 Sync 상태가 안정된다.
- Redis Operator CRD/Helm chart 버전을 클러스터 설정에서 직접 관리할 수 있어 refactor/gitops-sync-wave 브랜치 외부에서도 재사용이 용이해진다.


