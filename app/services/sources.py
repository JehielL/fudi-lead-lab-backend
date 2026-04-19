from typing import Annotated

from fastapi import Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.object_id import parse_object_id
from app.db.dependencies import get_database
from app.repositories.source_registry_repository import SourceRegistryRepository
from app.schemas.discovery import SourceRegistry, SourceRegistryCreate, SourceRegistryUpdate


class SourceService:
    def __init__(self, database: AsyncIOMotorDatabase):
        self.repository = SourceRegistryRepository(database)

    async def list_sources(self) -> list[SourceRegistry]:
        sources = await self.repository.list_sources()
        return [SourceRegistry.model_validate(source) for source in sources]

    async def create_source(self, payload: SourceRegistryCreate) -> SourceRegistry:
        existing = await self.repository.get_by_key(payload.sourceKey)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="sourceKey already exists")
        source = await self.repository.create_source(payload)
        return SourceRegistry.model_validate(source)

    async def update_source(self, source_id: str, payload: SourceRegistryUpdate) -> SourceRegistry:
        source = await self.repository.update_source(parse_object_id(source_id), payload)
        if source is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
        return SourceRegistry.model_validate(source)


def get_source_service(
    database: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
) -> SourceService:
    return SourceService(database)
