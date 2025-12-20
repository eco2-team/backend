"""Integration tests using testcontainers.

실제 PostgreSQL과 Redis 컨테이너를 사용한 통합 테스트.

Requirements:
    pip install testcontainers[postgres,redis] pytest-asyncio

Usage:
    pytest domains/character/tests/integration/ -v
"""
