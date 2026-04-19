from typing import Annotated

from fastapi import Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.object_id import parse_object_id
from app.db.dependencies import get_database
from app.repositories.raw_discovery_item_repository import RawDiscoveryItemRepository
from app.schemas.discovery import RawDiscoveryItem


class DiscoveryService:
    def __init__(self, database: AsyncIOMotorDatabase):
        self.repository = RawDiscoveryItemRepository(database)

    async def list_raw_items(self, limit: int) -> list[RawDiscoveryItem]:
        items = await self.repository.list_items(limit)
        return [RawDiscoveryItem.model_validate(item) for item in items]

    async def get_raw_item(self, item_id: str) -> RawDiscoveryItem:
        item = await self.repository.get_item(parse_object_id(item_id))
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Raw discovery item not found")
        return RawDiscoveryItem.model_validate(item)


def get_discovery_service(
    database: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
) -> DiscoveryService:
    return DiscoveryService(database)
