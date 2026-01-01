# Auth Relay

Redis Outbox에서 실패한 블랙리스트 이벤트를 RabbitMQ로 재발행하는 워커입니다.

## 아키텍처

```
auth-api (logout)
    │
    ├── 1차 시도: RabbitMQ 직접 발행 (성공률 ~99%)
    │
    └── 실패 시: Redis Outbox에 적재 (LPUSH)
            │
            └── Auth Relay Worker
                    │
                    └── RPOP → RabbitMQ 재발행
```

## Clean Architecture 구조

```
apps/auth_relay/
├── application/           # Use Cases
│   ├── commands/          # RelayEventCommand
│   └── common/
│       ├── dto/           # OutboxEvent
│       ├── ports/         # OutboxReader, EventPublisher
│       └── result.py      # RelayResult
├── infrastructure/        # 외부 시스템
│   ├── persistence_redis/ # RedisOutboxReader
│   └── messaging/         # RabbitMQEventPublisher
├── presentation/          # Relay Loop
│   └── relay_loop.py
├── setup/                 # 설정, DI
├── main.py
├── Dockerfile
└── requirements.txt
```

## 환경 변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `AUTH_REDIS_URL` | Redis 연결 URL | (필수) |
| `AUTH_AMQP_URL` | RabbitMQ 연결 URL | (필수) |
| `RELAY_POLL_INTERVAL` | 폴링 간격 (초) | 1.0 |
| `RELAY_BATCH_SIZE` | 배치 크기 | 10 |
| `LOG_LEVEL` | 로그 레벨 | INFO |

## Redis Keys

- `outbox:blacklist` - 실패한 이벤트 큐 (FIFO)
- `outbox:blacklist:dlq` - Dead Letter Queue (수동 처리 필요)

## 로컬 실행

```bash
# 환경 변수 설정
export AUTH_REDIS_URL="redis://localhost:6379/0"
export AUTH_AMQP_URL="amqp://guest:guest@localhost:5672/"

# 실행
python -m apps.auth_relay.main
```
