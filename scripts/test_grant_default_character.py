#!/usr/bin/env python3
"""기본 캐릭터 비동기 지급 테스트 스크립트.

Usage:
    # 로컬 테스트 (RabbitMQ 필요)
    python scripts/test_grant_default_character.py

    # Kubernetes Pod 내에서 테스트
    kubectl exec -it <users-api-pod> -n users -- python scripts/test_grant_default_character.py
"""

import asyncio
import os
import sys
from uuid import uuid4

# 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_celery_task_direct():
    """Celery 태스크 직접 호출 테스트."""
    print("\n=== 1. Celery 태스크 직접 호출 테스트 ===")

    try:
        from domains.character.tasks.grant_default import grant_default_character_task

        user_id = str(uuid4())
        print(f"테스트 user_id: {user_id}")

        # delay()로 비동기 실행
        result = grant_default_character_task.delay(user_id)
        print(f"Task ID: {result.id}")
        print(f"Task Status: {result.status}")

        # 결과 대기 (최대 30초)
        try:
            task_result = result.get(timeout=30)
            print(f"Task Result: {task_result}")
        except Exception as e:
            print(f"Task 대기 실패 (Worker가 실행 중인지 확인): {e}")

    except ImportError as e:
        print(f"Import 실패: {e}")
    except Exception as e:
        print(f"에러: {e}")


def test_celery_send_task():
    """send_task로 큐에 메시지 발행 테스트."""
    print("\n=== 2. send_task로 큐에 메시지 발행 ===")

    try:
        from celery import Celery

        broker_url = os.getenv(
            "CELERY_BROKER_URL",
            "amqp://guest:guest@localhost:5672/",
        )
        print(f"Broker URL: {broker_url}")

        app = Celery("test", broker=broker_url)

        user_id = str(uuid4())
        print(f"테스트 user_id: {user_id}")

        # send_task로 발행
        result = app.send_task(
            "character.grant_default",
            kwargs={"user_id": user_id},
            queue="character.grant_default",
        )
        print(f"Task ID: {result.id}")
        print("메시지 발행 완료! Worker가 처리할 것입니다.")

    except Exception as e:
        print(f"에러: {e}")


async def test_publisher_implementation():
    """CeleryDefaultCharacterPublisher 구현체 테스트."""
    print("\n=== 3. DefaultCharacterPublisher 구현체 테스트 ===")

    try:
        from celery import Celery

        from apps.users.infrastructure.messaging import CeleryDefaultCharacterPublisher

        broker_url = os.getenv(
            "CELERY_BROKER_URL",
            "amqp://guest:guest@localhost:5672/",
        )

        celery_app = Celery("users", broker=broker_url)
        publisher = CeleryDefaultCharacterPublisher(celery_app)

        user_id = uuid4()
        print(f"테스트 user_id: {user_id}")

        publisher.publish(user_id)
        print("이벤트 발행 완료! Worker가 처리할 것입니다.")

    except Exception as e:
        print(f"에러: {e}")


async def test_query_with_mock():
    """GetCharactersQuery 통합 테스트 (Mock)."""
    print("\n=== 4. GetCharactersQuery Mock 테스트 ===")

    try:
        from unittest.mock import AsyncMock, MagicMock

        from apps.users.application.character.queries import GetCharactersQuery
        from apps.users.setup.config import Settings

        # Mock gateway (빈 리스트)
        mock_gateway = MagicMock()
        mock_gateway.list_by_user_id = AsyncMock(return_value=[])

        # Mock publisher
        mock_publisher = MagicMock()

        # Settings
        settings = Settings()

        query = GetCharactersQuery(
            character_gateway=mock_gateway,
            default_publisher=mock_publisher,
            settings=settings,
        )

        user_id = uuid4()
        print(f"테스트 user_id: {user_id}")

        result = await query.execute(user_id)

        print(f"반환된 캐릭터 수: {len(result)}")
        if result:
            char = result[0]
            print(f"  - 이름: {char.character_name}")
            print(f"  - 코드: {char.character_code}")
            print(f"  - 타입: {char.character_type}")

        if mock_publisher.publish.called:
            print("✓ 이벤트 발행됨!")
            print(f"  - 호출된 user_id: {mock_publisher.publish.call_args}")
        else:
            print("✗ 이벤트 발행 안 됨")

    except Exception as e:
        print(f"에러: {e}")
        import traceback
        traceback.print_exc()


def check_rabbitmq_queue():
    """RabbitMQ 큐 상태 확인."""
    print("\n=== 5. RabbitMQ 큐 상태 확인 ===")

    try:
        import urllib.request
        import json

        # RabbitMQ Management API
        rabbitmq_host = os.getenv("RABBITMQ_HOST", "localhost")
        rabbitmq_mgmt_port = os.getenv("RABBITMQ_MGMT_PORT", "15672")
        rabbitmq_user = os.getenv("RABBITMQ_USER", "guest")
        rabbitmq_password = os.getenv("RABBITMQ_PASSWORD", "guest")
        vhost = os.getenv("RABBITMQ_VHOST", "%2F")  # URL encoded /

        url = f"http://{rabbitmq_host}:{rabbitmq_mgmt_port}/api/queues/{vhost}/character.grant_default"
        print(f"Checking: {url}")

        # Basic Auth
        import base64
        credentials = base64.b64encode(f"{rabbitmq_user}:{rabbitmq_password}".encode()).decode()

        request = urllib.request.Request(url)
        request.add_header("Authorization", f"Basic {credentials}")

        response = urllib.request.urlopen(request, timeout=5)
        data = json.loads(response.read())

        print(f"큐 이름: {data.get('name')}")
        print(f"메시지 수: {data.get('messages', 0)}")
        print(f"소비자 수: {data.get('consumers', 0)}")
        print(f"상태: {data.get('state')}")

    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("큐가 존재하지 않습니다. Worker가 시작되면 자동 생성됩니다.")
        else:
            print(f"HTTP 에러: {e}")
    except Exception as e:
        print(f"에러 (RabbitMQ Management API 접근 불가): {e}")


def main():
    """테스트 실행."""
    print("=" * 60)
    print("기본 캐릭터 비동기 지급 테스트")
    print("=" * 60)

    # 환경 확인
    print("\n환경 변수:")
    print(f"  CELERY_BROKER_URL: {os.getenv('CELERY_BROKER_URL', '(미설정)')}")
    print(f"  POSTGRES_HOST: {os.getenv('POSTGRES_HOST', '(미설정)')}")

    # 테스트 선택
    print("\n테스트 선택:")
    print("  1. Celery 태스크 직접 호출")
    print("  2. send_task로 큐에 발행")
    print("  3. DefaultCharacterPublisher 테스트")
    print("  4. GetCharactersQuery Mock 테스트")
    print("  5. RabbitMQ 큐 상태 확인")
    print("  a. 전체 실행")

    choice = input("\n선택 (1-5, a): ").strip().lower()

    if choice == "1":
        test_celery_task_direct()
    elif choice == "2":
        test_celery_send_task()
    elif choice == "3":
        asyncio.run(test_publisher_implementation())
    elif choice == "4":
        asyncio.run(test_query_with_mock())
    elif choice == "5":
        check_rabbitmq_queue()
    elif choice == "a":
        test_celery_task_direct()
        test_celery_send_task()
        asyncio.run(test_publisher_implementation())
        asyncio.run(test_query_with_mock())
        check_rabbitmq_queue()
    else:
        print("잘못된 선택")


if __name__ == "__main__":
    main()
