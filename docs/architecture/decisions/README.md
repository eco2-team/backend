# 💭 의사결정 과정 문서

> **검토 및 비교 분석 과정**  
> 최종 결정에 이르기까지의 논의 기록

## 📚 문서 목록

이 폴더의 문서들은 **검토 과정**을 기록한 것입니다. 실제 채택된 기술은 상위 폴더의 문서를 참고하세요.

### 배포 옵션 검토

1. **[배포 옵션 비교](deployment-options-comparison.md)**
   - Docker Compose vs ECS vs K8s 비교
   - 각 옵션의 장단점
   - 시나리오별 추천

### Kubernetes 옵션 검토

2. **[Self-managed K8s 분석](self-managed-k8s-analysis.md)**
   - EC2에 kubeadm 직접 구성 검토
   - 인건비 포함 비용 분석
   - 결론: 일반 사용자에게 부적합

3. **[k3s 구성 가이드](self-k8s-for-experts.md)**
   - 경량 K8s (k3s) 분석
   - 비용: $61/월
   - 결론: K8s 경험자에게 적합

4. **[EKS 비용 분석](eks-cost-breakdown.md)**
   - AWS EKS 최적화 비용 계산
   - 비용: $136/월
   - 결론: 경험자라면 고려 가능

5. **[EKS + ArgoCD GitOps](eks-argocd-gitops.md)**
   - 프로덕션급 GitOps 검토
   - 비용: $719/월 (인건비 포함)
   - 결론: 해커톤에 과도

### Docker Compose 옵션 검토

6. **[마이크로서비스 아키텍처](microservices-architecture.md)**
   - Docker Compose Multi-Service 검토
   - Traefik Gateway 설계
   - 결론: K8s로 최종 결정

7. **[GitOps 멀티서비스](gitops-multi-service.md)**
   - Docker Compose 기반 GitOps
   - Path-based Triggers
   - 결론: ArgoCD + Helm으로 전환

---

## ✅ 최종 결정

위 검토를 거쳐 **Kubernetes (kubeadm) + ArgoCD + Helm + RabbitMQ**를 채택했습니다.

**이유:**
- ✅ K8s 운영 경험 보유 (인건비 제외 가능)
- ✅ 비용 합리적 ($105/월)
- ✅ 프로덕션급 안정성 (ArgoCD, Helm, HPA)
- ✅ 도메인 완전 분리 (5개 Namespace)
- ✅ GitOps 자동화 (GitHub Actions + ArgoCD)
- ✅ IaC로 재현 가능 (Terraform + Ansible)
- ✅ Task Queue 최적화 (RabbitMQ, 5개 큐)

**vs Docker Compose:**
- Docker Compose는 개발용으로만 사용
- Kubernetes가 프로덕션 환경

**상세**: [최종 K8s 아키텍처](../final-k8s-architecture.md)

---

**이 폴더의 문서들은 참고용입니다.**  
**실제 구축은 상위 폴더의 최종 결정 문서를 따라주세요.**

