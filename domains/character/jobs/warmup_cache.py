"""
Character Cache Warmup Job

배포 시 PostSync Hook으로 실행되어 Worker 로컬 캐시를 워밍업합니다.
DB에서 캐릭터 목록을 조회하여 RabbitMQ fanout exchange로 브로드캐스트합니다.

Job 완료 후 명시적으로 exit(0)하여 K8s Job이 Completed 상태가 되도록 합니다.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time


async def warmup_cache() -> int:
    """DB에서 캐릭터 목록 조회 후 캐시 이벤트 발행.

    Returns:
        0: 성공, 1: 실패
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from domains._shared.cache import get_cache_publisher

    db_url = os.getenv("CHARACTER_DATABASE_URL")
    broker_url = os.getenv("CELERY_BROKER_URL")

    if not db_url:
        print("ERROR: CHARACTER_DATABASE_URL not set", flush=True)
        return 1

    if not broker_url:
        print("ERROR: CELERY_BROKER_URL not set", flush=True)
        return 1

    print(f"[{time.strftime('%H:%M:%S')}] Loading characters from DB...", flush=True)
    engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)

    try:
        async with engine.connect() as conn:
            # character 스키마의 characters 테이블에서 직접 조회
            result = await conn.execute(
                text(
                    "SELECT id, code, name, match_label, type_label, dialog "
                    "FROM character.characters"
                )
            )
            rows = result.fetchall()

        # 컬럼: id, code, name, match_label, type_label, dialog
        characters = []
        for row in rows:
            characters.append(
                {
                    "id": str(row[0]),
                    "code": row[1],
                    "name": row[2],
                    "match_label": row[3] or "",
                    "type_label": row[4] or "",
                    "dialog": row[5] or "",
                }
            )

        print(f"[{time.strftime('%H:%M:%S')}] Found {len(characters)} characters", flush=True)
        for c in characters[:3]:
            print(f"  - {c['name']} (match_label: {c['match_label']})", flush=True)

        # 캐시 refresh 이벤트 발행
        print(f"[{time.strftime('%H:%M:%S')}] Publishing cache refresh event...", flush=True)
        publisher = get_cache_publisher(broker_url)
        publisher.publish_full_refresh(characters)
        print(f"[{time.strftime('%H:%M:%S')}] Cache refresh event published!", flush=True)

        return 0

    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] ERROR: {e}", flush=True)
        return 1

    finally:
        await engine.dispose()
        print(f"[{time.strftime('%H:%M:%S')}] DB connection closed", flush=True)


def main() -> None:
    """Entry point - Job 완료 후 명시적 exit."""
    print("=== Cache Warmup Job Started ===", flush=True)
    exit_code = asyncio.run(warmup_cache())
    print(f"=== Cache Warmup Job Finished (exit={exit_code}) ===", flush=True)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
