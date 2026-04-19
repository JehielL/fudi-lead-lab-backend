from fastapi import APIRouter, Request

from app.schemas.health import HealthDependenciesResponse, HealthResponse
from app.services.health import check_dependencies

router = APIRouter()


@router.get("", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/dependencies", response_model=HealthDependenciesResponse)
async def health_dependencies(request: Request) -> HealthDependenciesResponse:
    return await check_dependencies(request.app.state)

