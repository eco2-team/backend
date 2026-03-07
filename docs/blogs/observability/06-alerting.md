# 이코에코(Eco²) Observability #6: 로그 기반 알림 연동

> **시리즈**: Eco² Observability Enhancement  
> **작성일**: 2025-12-17  
> **상태**: 📝 작성 예정  
> **태그**: `#Alerting` `#Elasticsearch` `#Slack` `#Watcher`

---

## 📋 개요

이 글에서는 로그 기반 알림 시스템을 구축하는 방법을 다룹니다. ERROR/CRITICAL 로그 발생 시 Slack/Discord로 알림을 전송합니다.

---

## 🎯 목표

1. Elasticsearch Watcher 설정
2. 알림 조건 정의 (ERROR 발생 시)
3. Slack Webhook 연동
4. 알림 템플릿 커스터마이징
5. 알림 노이즈 방지 (Throttling)

---

## 📝 내용 (작성 예정)

### 1. 알림 전략

| 조건 | 알림 채널 | Throttle |
|------|----------|----------|
| ERROR 로그 5개/분 | Slack #alerts | 5분 |
| CRITICAL 로그 발생 | Slack #critical + PagerDuty | 즉시 |
| 5xx 응답 급증 | Slack #alerts | 10분 |

### 2. Elasticsearch Watcher

```json
{
  "trigger": {
    "schedule": { "interval": "1m" }
  },
  "input": {
    "search": {
      "request": {
        "indices": ["logs-*"],
        "body": {
          "query": {
            "bool": {
              "must": [
                { "term": { "log.level": "error" } },
                { "range": { "@timestamp": { "gte": "now-5m" } } }
              ]
            }
          }
        }
      }
    }
  },
  "condition": {
    "compare": { "ctx.payload.hits.total.value": { "gt": 5 } }
  },
  "actions": {
    "slack_webhook": { ... }
  }
}
```

### 3. Slack Webhook 연동

### 4. 알림 템플릿

---

## 🔗 참고 자료

- [Elasticsearch Watcher](https://www.elastic.co/guide/en/elasticsearch/reference/current/watcher-api.html)
- [Kibana Alerting](https://www.elastic.co/guide/en/kibana/current/alerting-getting-started.html)

---

> ⚠️ **Note**: 이 글은 실제 구현 후 상세 내용이 추가될 예정입니다.

