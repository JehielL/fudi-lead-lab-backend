from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.security import get_current_user
from app.schemas.discovery import SourceRegistry, SourceRegistryCreate, SourceRegistryUpdate
from app.services.sources import SourceService, get_source_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[SourceRegistry])
async def list_sources(
    service: Annotated[SourceService, Depends(get_source_service)],
) -> list[SourceRegistry]:
    return await service.list_sources()


@router.post("", response_model=SourceRegistry, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: SourceRegistryCreate,
    service: Annotated[SourceService, Depends(get_source_service)],
) -> SourceRegistry:
    return await service.create_source(payload)


@router.patch("/{source_id}", response_model=SourceRegistry)
async def update_source(
    source_id: str,
    payload: SourceRegistryUpdate,
    service: Annotated[SourceService, Depends(get_source_service)],
) -> SourceRegistry:
    return await service.update_source(source_id, payload)
