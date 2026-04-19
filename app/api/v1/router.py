from fastapi import APIRouter

from app.api.v1.routers import auth, dedup, discovery, health, jobs, leads, models, ops, predictions, sources

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(leads.router, prefix="/leads", tags=["leads"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(sources.router, prefix="/sources", tags=["sources"])
api_router.include_router(discovery.router, prefix="/discovery", tags=["discovery"])
api_router.include_router(dedup.router, prefix="/dedup", tags=["dedup"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(predictions.router, prefix="/predictions", tags=["predictions"])
api_router.include_router(ops.router, prefix="/ops", tags=["ops"])
