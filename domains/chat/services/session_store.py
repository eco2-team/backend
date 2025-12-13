from __future__ import annotations

import json
from collections import deque
from datetime import datetime
from typing import Deque, Dict, Iterable, List

from redis.asyncio import Redis

from domains.chat.schemas.chat import ChatMessage


class ChatSessionStore:
    def __init__(
        self,
        redis: Redis | None,
        *,
        ttl_seconds: int,
        max_history: int,
    ) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds
        self.max_history = max_history
        self._memory: Dict[str, Deque[ChatMessage]] = {}

    def _key(self, user_id: str, session_id: str) -> str:
        return f"chat:session:{user_id}:{session_id}"

    async def append_messages(
        self,
        user_id: str,
        session_id: str,
        messages: Iterable[ChatMessage],
    ) -> None:
        batch = [self._serialize(msg) for msg in messages]
        if not batch:
            return
        key = self._key(user_id, session_id)
        if self.redis:
            pipeline = self.redis.pipeline()
            for payload in batch:
                pipeline.rpush(key, payload)
            pipeline.ltrim(key, -self.max_history, -1)
            pipeline.expire(key, self.ttl_seconds)
            await pipeline.execute()
            return

        history = self._memory.setdefault(key, deque(maxlen=self.max_history))
        for payload in batch:
            history.append(self._deserialize(payload))

    async def fetch_messages(self, user_id: str, session_id: str) -> List[ChatMessage]:
        key = self._key(user_id, session_id)
        if self.redis:
            raw_values = await self.redis.lrange(key, -self.max_history, -1)
            if raw_values:
                await self.redis.expire(key, self.ttl_seconds)
            return [self._deserialize(value) for value in raw_values]

        history = self._memory.get(key, deque())
        return list(history)

    async def delete_session(self, user_id: str, session_id: str) -> None:
        key = self._key(user_id, session_id)
        if self.redis:
            await self.redis.delete(key)
        else:
            self._memory.pop(key, None)

    def info(self) -> dict:
        return {
            "session_ttl_seconds": self.ttl_seconds,
            "session_history_limit": self.max_history,
            "backend": "redis" if self.redis else "memory",
        }

    def _serialize(self, message: ChatMessage) -> str:
        payload = message.model_dump()
        payload["timestamp"] = message.timestamp.isoformat()
        return json.dumps(payload, ensure_ascii=False)

    def _deserialize(self, payload: str) -> ChatMessage:
        data = json.loads(payload)
        timestamp = data.get("timestamp")
        if timestamp:
            data["timestamp"] = datetime.fromisoformat(timestamp)
        return ChatMessage(**data)
