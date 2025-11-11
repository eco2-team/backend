# 🏗️ 14-Node 아키텍처 Terraform 및 Ansible 구성

## 🎯 PR 목적

13-Node에서 14-Node로 확장하여 프로덕션 레벨의 Kubernetes 클러스터를 구성합니다. 도메인별 전용 노드 분리, CloudFront CDN 통합, EBS CSI Driver 추가 등 운영 환경에 필요한 모든 인프라를 구축합니다.

## 📝 주요 변경사항

### 🎯 14-Node 구성
- Master (1개): Control Plane
- API (7개): auth, my, scan, character, location, info, chat
- Worker (2개): storage, ai
- Infra (4개): postgresql, redis, rabbitmq, monitoring

### 💰 비용 최적화
- **총 리소스**: 28 vCPU, 30GB RAM
- **예상 비용**: $180-200/월
- **13-Node 대비**: +1 노드, 비용 증가 ~7%

---

자세한 내용은 커밋 메시지를 참조하세요.
