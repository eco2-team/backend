# dev-redis-operator OutOfSync 루프

## Symptoms
- ArgoCD에서 `dev-redis-operator`가 `Healthy`로 표시되지만 Sync 상태는 `OutOfSync`이며, 이벤트 로그에 `Partial sync`와 `Healthy -> Missing`이 수십 차례 반복된다.
- Sync 기록 상 동일 Revision을 반복해서 시도하지만 diffs가 사라지지 않는다.

## Diagnosis
1. ApplicationSet이 생성한 상위 Application 이름은 `dev-{{name}}` 패턴이라 Redis 항목에서 `dev-redis-operator`가 된다.
```1:34:clusters/dev/apps/25-data-operators.yaml
metadata:
  name: dev-{{name}}
```
2. `platform/helm/redis-operator` 경로도 자체 Application을 만들어 dev 오버레이에서 `namePrefix: dev-`를 붙인다.
```1:7:platform/helm/redis-operator/dev/kustomization.yaml
namePrefix: dev-
```
3. 결과적으로 동일 이름·네임스페이스(`argocd/dev-redis-operator`)의 Application을 상·하위에서 서로 apply하여 ownerReference/annotation이 계속 바뀌고, Argo는 이를 diff로 간주한다. 이 self-manage 루프 때문에 Health는 회복되나 Sync는 영구적인 OutOfSync 상태에 머문다.

## Fix
- App-of-App 패턴을 제거한다. ApplicationSet에서 Helm chart를 직접 지정하도록 바꾸고, `platform/helm/redis-operator` 디렉터리에 있던 Application 매니페스트는 삭제한다.
- 이름 충돌을 피하기 위해 상위 Application과 하위 리소스를 명확히 분리하거나, 상위만 남도록 구조를 단순화한다.

## Verification
1. `clusters/*/apps/25-data-operators.yaml`에서 Redis 항목이 Helm chart 정의를 직접 포함하는지 확인한다.
2. `platform/helm/redis-operator` 경로가 제거된 이후 `argocd app diff dev-redis-operator`를 실행하면 더 이상 Application 리소스 자체의 diff가 발생하지 않아야 한다.
3. Sync 이후 상태가 `Healthy/Synced`로 유지되는지 모니터링한다.


