# Image API Workload

Image 도메인 API 서비스 Kustomize 구조.

## 구조

- `base/`: Deployment, Service, ConfigMap 기본 템플릿
- `overlays/dev/`: dev 환경 설정
- `overlays/prod/`: prod 환경 설정

## 환경 변수

- `POSTGRES_HOST`: `postgresql.postgres.svc.cluster.local`
- `REDIS_HOST`: `redis.redis.svc.cluster.local`
- `IMAGE_CDN_DOMAIN`: CloudFront CNAME (예: `https://images.dev.growbin.app`) – 업로드/다운로드 모두 이 도메인을 사용

## 선행 조건

- Wave 35: Data Clusters
- Wave 58: `dockerhub-secret`
- SSM Parameter: `/sesacthon/{env}/api/image/{s3-bucket, cdn-domain}`

## 배포

```bash
kubectl apply -k workloads/domains/image/overlays/dev
```

## 로컬 테스트

```bash
cd domains/image
docker compose -f docker-compose.image-local.yml up --build
```

> `IMAGE_S3_BUCKET`, `IMAGE_CDN_DOMAIN`, `AWS_*` 자격 증명은 환경변수로 넘겨야 합니다. 기본 포트는 `http://127.0.0.1:8020`.
