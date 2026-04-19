from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING

from app.core.object_id import object_id_to_str


def serialize_enrichment_document(document: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(document)
    serialized["id"] = object_id_to_str(serialized.pop("_id", None))
    if "leadId" in serialized:
        serialized["leadId"] = object_id_to_str(serialized["leadId"])
    if "sourceSnapshotIds" in serialized:
        serialized["sourceSnapshotIds"] = [
            object_id_to_str(snapshot_id) for snapshot_id in serialized.get("sourceSnapshotIds", [])
        ]
    return serialized


class EnrichmentRepository:
    def __init__(self, database: AsyncIOMotorDatabase):
        self.page_snapshots = database.page_snapshots
        self.feature_snapshots = database.feature_snapshots

    async def create_page_snapshot(
        self,
        *,
        lead_id: ObjectId,
        url: str,
        snapshot_type: str,
        http_status: int | None,
        content_type: str | None,
        title: str | None,
        meta_description: str | None,
        text_extract: str | None,
        html_artifact_path: str | None = None,
    ) -> dict[str, Any]:
        document = {
            "leadId": lead_id,
            "url": url,
            "snapshotType": snapshot_type,
            "httpStatus": http_status,
            "contentType": content_type,
            "title": title,
            "metaDescription": meta_description,
            "textExtract": text_extract,
            "htmlArtifactPath": html_artifact_path,
            "capturedAt": datetime.now(UTC),
        }
        result = await self.page_snapshots.insert_one(document)
        created = await self.page_snapshots.find_one({"_id": result.inserted_id})
        return serialize_enrichment_document(created)

    async def list_page_snapshots(self, lead_id: ObjectId, limit: int = 20) -> list[dict[str, Any]]:
        cursor = self.page_snapshots.find({"leadId": lead_id}).sort("capturedAt", DESCENDING).limit(limit)
        return [serialize_enrichment_document(document) async for document in cursor]

    async def get_latest_page_snapshot(self, lead_id: ObjectId) -> dict[str, Any] | None:
        document = await self.page_snapshots.find_one({"leadId": lead_id}, sort=[("capturedAt", DESCENDING)])
        return serialize_enrichment_document(document) if document else None

    async def create_feature_snapshot(
        self,
        *,
        lead_id: ObjectId,
        version: int,
        features: dict[str, Any],
        derived_signals: dict[str, Any],
        source_snapshot_ids: list[str],
    ) -> dict[str, Any]:
        document = {
            "leadId": lead_id,
            "version": version,
            "features": features,
            "derivedSignals": derived_signals,
            "sourceSnapshotIds": [
                ObjectId(snapshot_id) for snapshot_id in source_snapshot_ids if ObjectId.is_valid(snapshot_id)
            ],
            "createdAt": datetime.now(UTC),
        }
        result = await self.feature_snapshots.insert_one(document)
        created = await self.feature_snapshots.find_one({"_id": result.inserted_id})
        return serialize_enrichment_document(created)

    async def list_feature_snapshots(self, lead_id: ObjectId, limit: int = 20) -> list[dict[str, Any]]:
        cursor = self.feature_snapshots.find({"leadId": lead_id}).sort("createdAt", DESCENDING).limit(limit)
        return [serialize_enrichment_document(document) async for document in cursor]

    async def get_latest_feature_snapshot(self, lead_id: ObjectId) -> dict[str, Any] | None:
        document = await self.feature_snapshots.find_one({"leadId": lead_id}, sort=[("createdAt", DESCENDING)])
        return serialize_enrichment_document(document) if document else None
