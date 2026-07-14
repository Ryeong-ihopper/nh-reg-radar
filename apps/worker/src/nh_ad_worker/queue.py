"""Minimal queue readiness boundary; job consumption begins in M4."""

from typing import Protocol

from redis.asyncio import Redis


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
