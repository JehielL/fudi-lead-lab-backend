import asyncio
from typing import Any

from minio.error import S3Error

from app.core.config import get_settings
from app.schemas.health import DependencyStatus, HealthDependenciesResponse, HealthStatus


async def _check_mongo(state: Any) -> DependencyStatus:
    settings = get_settings()
    try:
        await asyncio.wait_for(
            state.mongo_client.admin.command("ping"),
            timeout=settings.dependency_check_timeout_seconds,
        )
        return DependencyStatus(status="ok")
    except Exception as exc:
        return DependencyStatus(status="degraded", detail=str(exc))


async def _check_redis(state: Any) -> DependencyStatus:
    settings = get_settings()
    try:
        await asyncio.wait_for(
            state.redis_client.ping(),
            timeout=settings.dependency_check_timeout_seconds,
        )
        return DependencyStatus(status="ok")
    except Exception as exc:
        return DependencyStatus(status="degraded", detail=str(exc))


async def _check_minio(state: Any) -> DependencyStatus:
    settings = get_settings()

    def bucket_exists() -> bool:
        return state.minio_client.bucket_exists(settings.minio_bucket)

    try:
        await asyncio.wait_for(
            asyncio.to_thread(bucket_exists),
            timeout=settings.dependency_check_timeout_seconds,
        )
        return DependencyStatus(status="ok")
    except S3Error as exc:
        return DependencyStatus(status="degraded", detail=exc.message)
    except Exception as exc:
        return DependencyStatus(status="degraded", detail=str(exc))


def _rollup_status(dependencies: dict[str, DependencyStatus]) -> HealthStatus:
    if all(dependency.status == "ok" for dependency in dependencies.values()):
        return "ok"
    if any(dependency.status == "ok" for dependency in dependencies.values()):
        return "degraded"
    return "degraded"


async def check_dependencies(state: Any) -> HealthDependenciesResponse:
    mongo, redis, minio = await asyncio.gather(
        _check_mongo(state),
        _check_redis(state),
        _check_minio(state),
    )
    dependencies = {
        "mongodb": mongo,
        "redis": redis,
        "minio": minio,
    }
    return HealthDependenciesResponse(
        status=_rollup_status(dependencies),
        dependencies=dependencies,
    )
