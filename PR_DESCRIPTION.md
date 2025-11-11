# 📚 Monitoring & Troubleshooting 문서 전체 추가

## 🎯 PR 목적

운영 중 발생한 모든 트러블슈팅 케이스와 아키텍처 설계 문서를 체계적으로 정리하여 팀원 온보딩 및 장애 대응 시간을 단축합니다.
## 📝 주요 변경사항

### Troubleshooting 문서 (14개)
인프라, Ansible, Monitoring, ArgoCD, Atlantis, Database 관련 실전 트러블슈팅

### Architecture 문서 (7개)
Redis, WAL+MQ, Streaming vs Batch 등 설계 문서

### TROUBLESHOOTING.md 업데이트
14개 트러블슈팅 문서 인덱스 및 카테고리별 분류

## 📊 문서 구조

```
docs/
├── troubleshooting/ (14개)
│   ├── ALB_PROVIDER_ID.md
│   ├── ANSIBLE_SSH_TIMEOUT.md
│   ├── ARGOCD_*.md (2개)
│   ├── ATLANTIS_*.md (4개)
│   └── ...
│
├── architecture/ (7개)
│   ├── redis-*.md (2개)
│   ├── wal-*.md (3개)
│   └── chat-streaming-*.md (2개)
│
└── TROUBLESHOOTING.md
```

## 🎯 활용 방법

1. **문제 발생 시**: TROUBLESHOOTING.md에서 키워드 검색
2. **설계 검토 시**: architecture/ 문서 참조
3. **신규 팀원**: 주요 케이스 3-5개 읽기

## ✅ 체크리스트
- [x] Troubleshooting 14개
- [x] Architecture 7개
- [x] 인덱스 완료

---