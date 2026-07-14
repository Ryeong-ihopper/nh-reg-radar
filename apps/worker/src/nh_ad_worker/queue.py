"""Redis readiness and minimal M4 review-job delivery boundaries."""

import json
from typing import Any

from typing import Protocol

from redis.asyncio import Redis
from redis import Redis as SyncRedis


class QueueReadiness(Protocol):
    """Infrastructure contract needed before capability consumers exist."""

    async def ready(self) -> bool:
        """Return whether the queue transport accepts commands."""
        ...


class RedisQueueReadiness:
    """Redis implementation of the platform readiness contract."""

    def __init__(self, redis_url: str) -> None:
        self._client = Redis.from_url(redis_url, decode_responses=True)

    async def ready(self) -> bool:
        return bool(await self._client.ping())

    async def close(self) -> None:
        await self._client.aclose()


class RedisJobQueue:
    """Blocking list consumer; payload validation remains in ``QueueMessage``."""

    def __init__(
        self,
        redis_url: str,
        *,
        queue_name: str = "review-jobs-v1",
        dead_letter_name: str = "review-jobs-v1-dead-letter",
    ) -> None:
        self._client: Any = SyncRedis.from_url(redis_url, decode_responses=True)
        self._queue_name = queue_name
        self._dead_letter_name = dead_letter_name

    def pop(self, timeout: int = 1) -> dict[str, object] | None:
        item = self._client.blpop([self._queue_name], timeout=timeout)
        if item is None:
            return None
        _, body = item
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError("INVALID_REVIEW_QUEUE_MESSAGE")
        return payload

    def publish(self, payload: dict[str, str]) -> None:
        self._client.rpush(
            self._queue_name,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )

    def dead_letter(self, payload: dict[str, str]) -> None:
        self._client.rpush(
            self._dead_letter_name,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )

    def close(self) -> None:
        self._client.close()


class RedisDeadLetterSink:
    def __init__(self, queue: RedisJobQueue) -> None:
        self._queue = queue

    def publish(self, payload: dict[str, str]) -> None:
        self._queue.dead_letter(payload)
