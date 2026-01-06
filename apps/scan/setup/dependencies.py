"""Scan Dependencies - FastAPI Dependency Injection."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from scan.application.classify.commands import SubmitClassificationCommand
from scan.application.classify.ports import EventPublisher, IdempotencyCache
from scan.application.result.ports import ResultCache
from scan.application.result.queries import GetCategoriesQuery, GetResultQuery
from scan.infrastructure.persistence_redis import (
    EventPublisherRedis,
    IdempotencyCacheRedis,
    ResultCacheRedis,
)
from scan.setup.celery_app import celery_app
from scan.setup.config import Settings, get_settings

# ─────────────────────────────────────────────────────────────────────────────
# Infrastructure Dependencies
# ─────────────────────────────────────────────────────────────────────────────


@lru_cache
def get_event_publisher() -> EventPublisher:
    """Event Publisher 인스턴스 반환."""
    return EventPublisherRedis()


@lru_cache
def get_result_cache() -> ResultCache:
    """Result Cache 인스턴스 반환."""
    settings = get_settings()
    return ResultCacheRedis(
        redis_url=settings.redis_cache_url,
        default_ttl=settings.result_cache_ttl,
    )


@lru_cache
def get_idempotency_cache() -> IdempotencyCache:
    """Idempotency Cache 인스턴스 반환."""
    return IdempotencyCacheRedis()


# ─────────────────────────────────────────────────────────────────────────────
# Application Dependencies (Commands / Queries)
# ─────────────────────────────────────────────────────────────────────────────


def get_submit_command(
    event_publisher: Annotated[EventPublisher, Depends(get_event_publisher)],
    idempotency_cache: Annotated[IdempotencyCache, Depends(get_idempotency_cache)],
) -> SubmitClassificationCommand:
    """Submit Classification Command 인스턴스 반환."""
    return SubmitClassificationCommand(
        event_publisher=event_publisher,
        idempotency_cache=idempotency_cache,
        celery_app=celery_app,
    )


def get_result_query(
    result_cache: Annotated[ResultCache, Depends(get_result_cache)],
) -> GetResultQuery:
    """Get Result Query 인스턴스 반환."""
    return GetResultQuery(result_cache=result_cache)


def get_categories_query() -> GetCategoriesQuery:
    """Get Categories Query 인스턴스 반환.

    Note:
        카테고리 목록은 정적 데이터이므로 외부 의존성 없이 반환합니다.
        실제 RAG (배출 규정 검색)는 scan_worker에서 수행합니다.
    """
    return GetCategoriesQuery()


# ─────────────────────────────────────────────────────────────────────────────
# Type Aliases for Dependency Injection
# ─────────────────────────────────────────────────────────────────────────────


SettingsDep = Annotated[Settings, Depends(get_settings)]
EventPublisherDep = Annotated[EventPublisher, Depends(get_event_publisher)]
ResultCacheDep = Annotated[ResultCache, Depends(get_result_cache)]
SubmitCommandDep = Annotated[SubmitClassificationCommand, Depends(get_submit_command)]
GetResultQueryDep = Annotated[GetResultQuery, Depends(get_result_query)]
GetCategoriesQueryDep = Annotated[GetCategoriesQuery, Depends(get_categories_query)]
