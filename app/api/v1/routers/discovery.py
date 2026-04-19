from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.security import get_current_user
from app.schemas.discovery import RawDiscoveryItem
from app.services.discovery import DiscoveryService, get_discovery_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/raw-items", response_model=list[RawDiscoveryItem])
async def list_raw_items(
    service: Annotated[DiscoveryService, Depends(get_discovery_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[RawDiscoveryItem]:
    return await service.list_raw_items(limit)


@router.get("/raw-items/{item_id}", response_model=RawDiscoveryItem)
async def get_raw_item(
    item_id: str,
    service: Annotated[DiscoveryService, Depends(get_discovery_service)],
) -> RawDiscoveryItem:
    return await service.get_raw_item(item_id)
