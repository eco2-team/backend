# 2025-11 CI Services Docker Hub 전환 기록

- **작업 기간**: 2025-11-18 ~ 2025-11-19  
- **대상 브랜치**: `refactor/gitops-sync-wave` (테스트용), `main`, `develop`  
- **키워드**: GHCR → Docker Hub 마이그레이션, 태그 전략 정비, Secret 체계 변경

---

## 1. 배경

1. GHCR 접근 토큰 관리 요건이 충돌, public으로 공개해도 무관하기에 Docker Hub(`docker.io/mng990/eco2:*`)를 단일 진실 공급원으로 쓰기로 결정.
2. API 이미지는 GitOps 매니페스트(Deployment/Kustomize)에서 직접 참조하므로, CI에서 빌드하는 태그/이름과 클러스터가 풀하는 값이 **완전히 일치**해야 한다.
3. 테스트·검증은 `refactor/gitops-sync-wave` 브랜치에서 먼저 수행한 뒤 `main`/`develop`으로 확장하고, CI 실패 없이 모든 파이프라인이 통과해야만 배포를 진행한다.
4. Harbor 도입도 검토하였으나, 일정이 촉박한 관계로 차후 일정으로 이관

---

## 2. 설계 결정 요약

| 항목 | 결정 |
|------|------|
| 레지스트리 | `docker.io/mng990/eco2` (단일 리포) |
| 태그 정책 | `{service}-api-dev-{sha6}` / `{service}-api-dev-latest` (develop), `{service}-api-{VERSION}-{sha6}` / `{service}-api-prod-latest` / `{service}-api-latest` (main push) |
| Secret 명칭 | Kubernetes `dockerhub-secret`, ExternalSecret `dockerhub-pull-secret` |
| 자격 증명 저장소 | AWS SSM `/sesacthon/dockerhub/{username,password}` + GitHub Actions `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` |
| 브랜치 트리거 | `main`, `develop`, `refactor/gitops-sync-wave` push/PR |

---

## 3. 구현 상세

### 3.1 워크플로 트리거/경로 확장

`ci-services.yml`은 Docker Hub 마이그레이션 검증을 위해 `refactor/gitops-sync-wave` 브랜치까지 트리거에 포함했고, 서비스/스크립트/워크플로 경로 변경에만 반응하도록 유지했다.

```3:21:.github/workflows/ci-services.yml
on:
  push:
    branches:
      - main
      - develop
      - refactor/gitops-sync-wave
    paths:
      - "services/**"
      - "scripts/**"
      - ".github/workflows/ci-services.yml"
  pull_request:
    branches:
      - main
      - develop
      - refactor/gitops-sync-wave
```

### 3.2 Docker Hub 로그인과 태그 생성기

CI에서 `docker/login-action@v3`를 Docker Hub 자격증명으로 로그인하도록 바꾸고, Buildx 단계 전에 태그를 계산하는 `Prepare image tags` 스텝을 추가했다. `main`에서 직접 push 되는 커밋만 프로덕션 태그를 만들고, 그 외 브랜치는 dev 태그만 생성한다.

```201:239:.github/workflows/ci-services.yml
      - name: Login to Docker Hub
        uses: docker/login-action@v3
        with:
          registry: docker.io
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      - name: Prepare image tags
        id: meta
        run: |
          SHORT_SHA=$(git rev-parse --short=6 HEAD)
          SERVICE="${{ matrix.service }}"
          IMAGE_REPO="docker.io/mng990/eco2"
          SERVICE_SLUG="${SERVICE}-api"
          ...
          if [ "$BASE_REF" = "main" ] && [ "$IS_PR" = "false" ]; then
            UNIQUE_TAG="${SERVICE_SLUG}-${VERSION}-${SHORT_SHA}"
            {
              echo "tags<<TAGS"
              echo "${IMAGE_REPO}:${UNIQUE_TAG}"
              echo "${IMAGE_REPO}:${SERVICE_SLUG}-prod-latest"
              echo "${IMAGE_REPO}:${SERVICE_SLUG}-latest"
              echo "TAGS"
            } >> "$GITHUB_OUTPUT"
          else
            {
              echo "tags<<TAGS"
              echo "${IMAGE_REPO}:${SERVICE_SLUG}-dev-${SHORT_SHA}"
              echo "${IMAGE_REPO}:${SERVICE_SLUG}-dev-latest"
              echo "TAGS"
            } >> "$GITHUB_OUTPUT"
          fi
```

Buildx는 `steps.meta.outputs.tags` 값을 그대로 사용해 멀티 태그 푸시를 수행한다.

```241:247:.github/workflows/ci-services.yml
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: services/${{ matrix.service }}
          file: services/${{ matrix.service }}/Dockerfile
          push: true
          tags: ${{ steps.meta.outputs.tags }}
```

### 3.3 클러스터 매니페스트 정합성

CI가 생성하는 태그는 GitOps 오버레이가 그대로 참조하도록 모든 Deployment/Kustomize 정의를 Docker Hub 주소로 교체했다.

- **Deployment 기본 이미지**: `dockerhub-secret`을 통해 풀하며 `docker.io/mng990/eco2:latest`를 기본값으로 두고 태그로 서비스/환경을 구분한다.

```23:51:workloads/apis/auth/base/deployment.yaml
        - name: auth-api
          image: docker.io/mng990/eco2:latest
...
      imagePullSecrets:
        - name: dockerhub-secret
```

- **환경별 오버레이**: dev/prod 각각 `name: docker.io/mng990/eco2`에 `newTag: <service>-<env>-latest`를 부여해 동일 리포 내 태그만 바꾸도록 했다.

```1:14:workloads/apis/auth/prod/kustomization.yaml
images:
- name: docker.io/mng990/eco2
  newTag: auth-prod-latest
```

### 3.4 Secret 공급 경로

ExternalSecret에서 AWS SSM `/sesacthon/dockerhub/{username,password}` 키를 읽어 `dockerhub-secret`(Kubernetes `dockerconfigjson`)을 생성하도록 템플릿을 새로 작성했다. 동일 정의를 auth/my/scan/character/location/info/chat 네임스페이스에 복제했다.

```1:35:workloads/secrets/external-secrets/dev/dockerhub-pull-secret.yaml
  data:
    - secretKey: username
      remoteRef:
        key: /sesacthon/dockerhub/username
    - secretKey: password
      remoteRef:
        key: /sesacthon/dockerhub/password
  target:
    name: dockerhub-secret
...
            "auths": {
              "https://index.docker.io/v1/": {
                "username": "{{ .username }}",
                "password": "{{ .password }}"
```

---

## 4. 검증 및 운영 체크리스트

1. **브랜치별 파이프라인**: `develop`은 dev 태그만 생성하므로, prod 태그는 반드시 `main` push에서만 나온다. PR 병합 전에 반드시 어떤 브랜치인지 확인.
2. **Secret 생성 확인**: `kubectl get secret dockerhub-secret -n <ns>` 로 모든 비즈니스 네임스페이스에 Secret이 생기는지 확인하고, `kubectl get pod -n <ns> -o jsonpath='{.items[*].spec.imagePullSecrets}'` 로 참조 여부를 모니터링.
3. **이미지 경로 검증**: `kubectl get deploy -n auth auth-api -o yaml | yq '.spec.template.spec.containers[0].image'` 등이 CI 태그와 일치하는지 확인한다.
4. **레이트 리밋**: Docker Hub Free 계정은 Pull 제한이 있으므로 Team/Pro 플랜을 권장하고, 캐싱이 필요하면 사내 Registry Mirror(아티팩트리 등)를 검토한다.
5. **토큰 관리**: 명령어 입력 시 `gh secret set` 또는 `aws ssm put-parameter --value fileb://` 패턴을 사용해 셸 히스토리를 남기지 않는다. 토큰 노출이 의심되면 `dockerhub.com`에서 즉시 재발급한다.

---

## 5. 후속 계획

- `docs/ci/GITHUB_ACTIONS_CI_QUALITY_GATE.md`의 이미지 관련 단락을 Docker Hub 기준으로 갱신하고, 향후 SonarQube/커버리지 연계를 추가할 때도 동일 태그 규칙을 사용한다.
- `refactor/gitops-sync-wave` 브랜치에서 충분히 테스트한 뒤, 브랜치 보호 정책에 반영해 `main`/`develop` 모두에서 Docker Hub 태그가 강제되도록 한다.
- 필요 시 Harbor 같은 온프레미스 레지스트리 도입 시에도 이 문서를 템플릿으로 활용해 변경 로그를 남긴다.

> 본 문서는 CI 파이프라인 변경 히스토리를 추적하기 위한 기록이며, 추가 수정 시 날짜/결정사항/근거를 함께 업데이트한다.

