#!/bin/bash

# ==========================================
# Eco2 Scan API Load Testing Script
# ==========================================

# 1. 사용자 입력 처리 (동시 접속자 수)
if [ -z "$1" ]; then
    echo "Usage: $0 <concurrency>"
    echo "Example: $0 5"
    exit 1
fi

CONCURRENCY=$1

# 2. 설정
COOKIE_VAL="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIzZTkyNGFmYS05MjU1LTRiZTktOTRmMS1iNzliOWVkNjg3YmEiLCJqdGkiOiJlMGZjMmFmNi04NTRhLTRiNWYtYTg5Mi0yMmVlNmY5NzRkODkiLCJ0eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzY1MTc4Nzg4LCJpYXQiOjE3NjQ5MTk1ODgsImlzcyI6InNlc2FjdGhvbi1hdXRoIiwiYXVkIjoic2VzYWN0aG9uLWNsaWVudHMiLCJwcm92aWRlciI6Imtha2FvIn0.QN76cM-0WOXIbMqONzMPcOac27gthdSRX_Sy7xMa6Jk"
URL="https://api.dev.growbin.app/api/v1/scan/classify"
BODY='{"image_url": "https://images.dev.growbin.app/scan/1e89074f111d4727b1f28da647bc7c8e.jpg", "user_input": ""}'

# 각 요청 사이 대기 시간 (초)
DELAY=0

# 시작 시간 기록
START_TIME=$(date +%s)

echo "🚀 Starting Load Test with $CONCURRENCY parallel users..."
echo "🎯 Target: $URL"
echo "⏳ Delay per user: ${DELAY}s"
echo "🕒 Start Time: $(date)"
echo "---------------------------------------------------"

# 3. 종료 시그널 처리
trap "kill 0" SIGINT

# 4. 병렬 루프 실행
for i in $(seq 1 $CONCURRENCY); do
    (
        while true; do
            # 경과 시간 계산
            CURRENT_TIME=$(date +%s)
            ELAPSED_SEC=$((CURRENT_TIME - START_TIME))
            ELAPSED_FMT=$(printf "%02d:%02d" $((ELAPSED_SEC/60)) $((ELAPSED_SEC%60)))

            # curl 실행
            curl -X POST "$URL" \
              -H "Content-Type: application/json" \
              -H "Cookie: s_access=$COOKIE_VAL" \
              -d "$BODY" \
              -s -o /dev/null \
              -w "[$ELAPSED_FMT] User $i: Status %{http_code} | Time %{time_total}s\n"

            sleep $DELAY
        done
    ) &
    sleep 0.5
done

# 5. 무한 대기
wait
