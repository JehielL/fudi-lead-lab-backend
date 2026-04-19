from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING

from app.core.object_id import object_id_to_str
from app.schemas.discovery import SourceRegistryCreate, SourceRegistryUpdate


def serialize_source(document: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(document)
    serialized["id"] = object_id_to_str(serialized.pop("_id", None))
    return serialized


class SourceRegistryRepository:
    def __init__(self, database: AsyncIOMotorDatabase):
        self.collection = database.source_registry

    async def list_sources(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        query = {"isEnabled": True} if enabled_only else {}
        cursor = self.collection.find(query).sort("priority", ASCENDING)
        return [serialize_source(document) async for document in cursor]

    async def get_source(self, source_id: ObjectId) -> dict[str, Any] | None:
        document = await self.collection.find_one({"_id": source_id})
        return serialize_source(document) if document else None

    async def get_by_key(self, source_key: str) -> dict[str, Any] | None:
        document = await self.collection.find_one({"sourceKey": source_key})
        return serialize_source(document) if document else None

    async def create_source(self, payload: SourceRegistryCreate) -> dict[str, Any]:
        now = datetime.now(UTC)
        document = payload.model_dump()
        document["createdAt"] = now
        document["updatedAt"] = now
        result = await self.collection.insert_one(document)
        created = await self.collection.find_one({"_id": result.inserted_id})
        return serialize_source(created)

    async def update_source(
        self,
        source_id: ObjectId,
        payload: SourceRegistryUpdate,
    ) -> dict[str, Any] | None:
        update_data = payload.model_dump(exclude_unset=True)
        if update_data:
            update_data["updatedAt"] = datetime.now(UTC)
            await self.collection.update_one({"_id": source_id}, {"$set": update_data})
        return await self.get_source(source_id)

    async def count_enabled(self) -> int:
        return await self.collection.count_documents({"isEnabled": True})
