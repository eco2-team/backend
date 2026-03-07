# 이코에코(Eco²) Clean Architecture 시리즈

Auth 도메인 Clean Architecture 리팩토링 기록.

## 목차

| # | 제목 | 내용 |
|---|------|------|
| 1 | [설계](./01-auth-design.md) | DIP, Port & Adapter, CQRS, 폴더 구조 |
| 2 | [구현](./02-auth-implementation.md) | Entity, Value Object, Use Case, Adapter |
| 3 | [CI/CD](./03-auth-cicd.md) | Canary 배포, GitHub Actions, ArgoCD |

## 기술 스택

- Python 3.11
- FastAPI
- SQLAlchemy 2.0 (async)
- Redis
- JWT (python-jose)
- Kubernetes + Istio
- ArgoCD + Image Updater

## 참고 프로젝트

- [fastapi-clean-example](https://github.com/ivan-borovets/fastapi-clean-example)









