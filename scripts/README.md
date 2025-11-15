# Scripts Directory

현재는 **connect-ssh.sh** 단일 스크립트만 유지합니다.  
선언형 GitOps 구축 이후 수동 운영 스크립트를 모두 제거했고, 클러스터 접속 헬퍼만 남았습니다.

```
scripts/
├── README.md
└── utilities/
    └── connect-ssh.sh
```

| 스크립트 | 목적 | 사용 예시 |
|----------|------|-----------|
| `connect-ssh.sh` | SSH 접속 헬퍼 (호스트 키 무시) | `bash scripts/utilities/connect-ssh.sh <NODE_IP>` |

새로운 스크립트가 필요하면 최소한으로 추가하고, README를 반드시 갱신해 주세요.

