# 코드 품질 분석 도구 도입기

> 2025.12.20

## 목차

1. [배경](#배경)
2. [도입 도구](#도입-도구)
3. [Radon 설정 및 사용](#radon-설정-및-사용)
4. [SonarCloud 연동](#sonarcloud-연동)
5. [실측 결과](#실측-결과)
6. [결론](#결론)

---

## 배경

코드 품질을 객관적으로 측정하고 지속적으로 모니터링하기 위해 정적 분석 도구를 도입했습니다.

### 도구 선정 기준

| 기준 | 설명 |
|------|------|
| **비용** | 무료 또는 오픈소스 Public repo 무료 |
| **Python 지원** | Python 3.11 호환 |
| **CI 연동** | GitHub Actions 통합 가능 |
| **선언적 설정** | 코드베이스에서 설정 관리 |

---

## 도입 도구

| 도구 | 용도 | 비용 |
|------|------|------|
| **Radon** | Cyclomatic Complexity, Maintainability Index | 무료 (로컬 CLI) |
| **SonarCloud** | 종합 코드 품질, 보안 취약점 | Public repo 무료 |

---

## Radon 설정 및 사용

### 설치

```bash
pip install radon
```

### 설정 (pyproject.toml)

```toml
[tool.radon]
exclude = "test_*,*_test.py,conftest.py,__pycache__,worktrees,.venv"
cc_min = "C"  # Minimum grade to show (A=best, F=worst)
mi_min = "B"  # Maintainability Index minimum grade
show_complexity = true
average = true
```

### 사용법

```bash
# Cyclomatic Complexity 측정
radon cc domains/ -a -s

# Maintainability Index 측정
radon mi domains/ -s

# Raw 메트릭 (LOC, LLOC 등)
radon raw domains/ -s
```

### 복잡도 등급

| 등급 | 복잡도 범위 | 의미 |
|------|------------|------|
| A | 1-5 | 단순, 위험 낮음 |
| B | 6-10 | 약간 복잡 |
| C | 11-20 | 복잡, 리팩토링 권장 |
| D | 21-30 | 매우 복잡 |
| F | 31+ | 테스트 불가 수준 |

---

## SonarCloud 연동

### 프로젝트 설정 (sonar-project.properties)

```properties
# Project identification
sonar.projectKey=eco2-team_backend
sonar.organization=eco2-team
sonar.projectName=backend

# Source settings
sonar.sources=domains
sonar.tests=domains
sonar.test.inclusions=**/tests/**,**/test_*.py,**/*_test.py
sonar.exclusions=\
  **/tests/**,\
  **/test_*.py,\
  **/*_test.py,\
  **/conftest.py,\
  **/*_pb2.py,\
  **/*_pb2_grpc.py,\
  **/proto/**

# Python settings
sonar.python.version=3.11
sonar.python.coverage.reportPaths=coverage.xml

# Coverage exclusions
sonar.coverage.exclusions=\
  **/tests/**,\
  **/proto/**,\
  **/*_pb2.py,\
  **/*_pb2_grpc.py
```

### GitHub Actions Workflow

```yaml
# .github/workflows/ci-sonarcloud.yml
name: SonarCloud Analysis

on:
  workflow_dispatch:
  push:
    branches: [develop, main]
    paths:
      - 'domains/**/*.py'
      - 'sonar-project.properties'

jobs:
  sonarcloud:
    name: 🔍 SonarCloud Scan
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r domains/character/requirements.txt
          pip install pytest pytest-cov pytest-asyncio

      - name: Run tests with coverage
        run: |
          pytest domains/character/tests/ \
            --cov=domains/character \
            --cov-report=xml:coverage.xml \
            --ignore=domains/character/tests/integration/ \
            --ignore=domains/character/tests/e2e/
        continue-on-error: true

      - uses: SonarSource/sonarcloud-github-action@master
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
```

### 플랜 및 제한사항

SonarCloud는 **유료 플랜 구독 시** PR/feature 브랜치 분석을 지원합니다.

| 플랜 | 브랜치 분석 | PR 분석 | 가격 |
|------|------------|---------|------|
| Free (Public) | main만 | ❌ | 무료 |
| Developer+ | 모든 브랜치 | ✅ | 유료 |

**현재 적용**: 무료 플랜 사용으로 **main/develop 브랜치 머지 후에만** 분석 실행.

```yaml
# PR 분석은 유료 플랜 필요 - 현재 미사용
# main/develop 머지 후에만 분석 실행
on:
  push:
    branches: [develop, main]
  # pull_request: 유료 플랜 필요
```

---

## 실측 결과

### Radon Cyclomatic Complexity

```
실행: radon cc domains/ -a -s --total-average

결과:
- 총 블록: 1,004개
- 평균 복잡도: A (2.51)
- A등급: 997개 (99.3%)
- B등급: 7개 (0.7%)
- C등급 이상: 0개
```

### 개선 전후 비교

| 지표 | 개선 전 | 개선 후 |
|------|---------|---------|
| 총 블록 | 992개 | 1,004개 |
| 평균 복잡도 | A (2.53) | A (2.51) |
| C등급 함수 | 7개 | **0개** |
| D/F등급 | 0개 | 0개 |

### 테스트 커버리지

```
실행: pytest --cov=domains/character/services --cov-report=term-missing

결과:
- services/character.py: 91%
- services/evaluators/base.py: 100%
- services/evaluators/scan.py: 97%
- services/evaluators/registry.py: 83%
- 전체: 92%
```

---

## 결론

### 도입 효과

1. **객관적 품질 지표**: 복잡도, 커버리지 수치화
2. **지속적 모니터링**: CI에서 자동 분석
3. **선언적 설정**: 코드베이스에서 버전 관리

### 권장 사용 패턴

```bash
# 로컬 개발 시 - Radon으로 빠른 체크
radon cc domains/my_module/ -a -s

# PR 머지 전 - pytest 커버리지 확인
pytest --cov=domains/my_module --cov-report=term-missing

# 머지 후 - SonarCloud 대시보드 확인
https://sonarcloud.io/dashboard?id=eco2-team_backend
```

### 목표 지표

| 지표 | 목표 | 현재 |
|------|------|------|
| 평균 복잡도 | A | ✅ A (2.51) |
| C등급 함수 | 0개 | ✅ 0개 |
| 서비스 커버리지 | 80%+ | ✅ 92% |

---

## Reference

- [Radon Documentation](https://radon.readthedocs.io/)
- [SonarCloud Documentation](https://docs.sonarcloud.io/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)
