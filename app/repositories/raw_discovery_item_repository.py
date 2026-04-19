from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING

from app.core.object_id import object_id_to_str


def serialize_raw_item(document: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(document)
    serialized["id"] = object_id_to_str(serialized.pop("_id", None))
    serialized["createdLeadId"] = object_id_to_str(serialized.get("createdLeadId"))
    return serialized


class RawDiscoveryItemRepository:
    def __init__(self, database: AsyncIOMotorDatabase):
        self.collection = database.raw_discovery_items

    async def list_items(self, limit: int = 50) -> list[dict[str, Any]]:
        cursor = self.collection.find({}).sort("createdAt", DESCENDING).limit(limit)
        return [serialize_raw_item(document) async for document in cursor]

    async def get_item(self, item_id: ObjectId) -> dict[str, Any] | None:
        document = await self.collection.find_one({"_id": item_id})
        return serialize_raw_item(document) if document else None

    async def create_item(
        self,
        *,
        source_type: str,
        source_key: str,
        external_id: str | None,
        source_url: str | None,
        raw_payload: dict[str, Any],
    ) -> dict[str, Any]:
        document = {
            "sourceType": source_type,
            "sourceKey": source_key,
            "externalId": external_id,
            "sourceUrl": source_url,
            "rawPayload": raw_payload,
            "normalizedPayload": {},
            "processed": False,
            "processedAt": None,
            "createdLeadId": None,
            "createdAt": datetime.now(UTC),
        }
        result = await self.collection.insert_one(document)
        created = await self.collection.find_one({"_id": result.inserted_id})
        return serialize_raw_item(created)

    async def mark_processed(
        self,
        item_id: ObjectId,
        *,
        normalized_payload: dict[str, Any],
        created_lead_id: ObjectId | None,
    ) -> dict[str, Any]:
        await self.collection.update_one(
            {"_id": item_id},
            {
                "$set": {
                    "normalizedPayload": normalized_payload,
                    "processed": True,
                    "processedAt": datetime.now(UTC),
                    "createdLeadId": created_lead_id,
                }
            },
        )
        updated = await self.collection.find_one({"_id": item_id})
        return serialize_raw_item(updated)
