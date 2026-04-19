from redis.asyncio import Redis

from app.core.config import Settings


def get_redis_client(settings: Settings) -> Redis:
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=settings.dependency_check_timeout_seconds,
        socket_timeout=settings.dependency_check_timeout_seconds,
    )


async def close_redis_client(client: Redis) -> None:
    await client.aclose()

