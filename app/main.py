from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.indexes import ensure_indexes
from app.db.minio import close_minio_client, get_minio_client
from app.db.mongo import close_mongo_client, get_mongo_client
from app.db.redis import close_redis_client, get_redis_client
from app.middleware.request_id import RequestIdMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    app.state.mongo_client = get_mongo_client(settings)
    app.state.redis_client = get_redis_client(settings)
    app.state.minio_client = get_minio_client(settings)
    await ensure_indexes(app.state.mongo_client[settings.mongodb_database])
    yield
    await close_redis_client(app.state.redis_client)
    close_mongo_client(app.state.mongo_client)
    close_minio_client(app.state.minio_client)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
