# 🏗️ Infrastructure 문서

> **4-Node Kubernetes 클러스터 인프라**  
> **Terraform + Ansible + AWS**

## 📚 문서 목록

### 네트워크 설계

1. **[VPC 네트워크 설계](vpc-network-design.md)** ⭐⭐⭐⭐⭐
   - VPC (10.0.0.0/16)
   - 3 Public Subnets
   - Security Groups 전체
   - 포트 목록 상세

### Kubernetes 구축

2. **[K8s 클러스터 구축 (4-Node)](k8s-cluster-setup.md)** ⭐⭐⭐⭐
   - kubeadm 수동 설치 가이드
   - 4-node 구성
   - 단계별 명령어

3. **[IaC 구성 (Terraform + Ansible)](iac-terraform-ansible.md)** ⭐⭐⭐⭐⭐
   - 자동화 스크립트
   - Terraform 구조
   - Ansible Playbook
   - 40-50분 자동 배포

### CNI

4. [CNI 비교 (Calico vs Flannel)](cni-comparison.md)
   - Flannel → Calico 전환
   - VXLAN vs BGP
   - 성능 비교

---

## 🎯 빠른 참조

```
자동 배포:
./scripts/auto-rebuild.sh

수동 배포:
1. VPC 네트워크 설계 참고
2. Terraform으로 인프라 생성
3. Ansible로 Kubernetes 설치
4. k8s-cluster-setup.md 참고

구성:
- 4 nodes (Master + 3 Workers)
- 8 vCPU, 24GB RAM
- $180/month
```

---

**최종 업데이트**: 2025-10-31  
**상태**: 프로덕션 준비 완료
