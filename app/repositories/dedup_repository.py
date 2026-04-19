from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING

from app.core.object_id import object_id_to_str


def serialize_dedup_document(document: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(document)
    serialized["id"] = object_id_to_str(serialized.pop("_id", None))
    for key in ("leadIds", "candidateIds", "mergedLeadIds"):
        if key in serialized:
            serialized[key] = [object_id_to_str(value) for value in serialized.get(key, [])]
    for key in ("clusterId", "primaryLeadId", "mergedIntoLeadId"):
        if key in serialized and serialized[key] is not None:
            serialized[key] = object_id_to_str(serialized[key])
    return serialized


class DedupRepository:
    def __init__(self, database: AsyncIOMotorDatabase):
        self.database = database
        self.leads = database.leads
        self.sources = database.lead_sources
        self.activities = database.lead_activities
        self.candidates = database.dedup_candidates
        self.clusters = database.dedup_clusters
        self.merge_events = database.merge_events

    async def list_candidate_documents(self, status: str = "open", limit: int = 100) -> list[dict[str, Any]]:
        cursor = self.candidates.find({"status": status}).sort("score", DESCENDING).limit(limit)
        return [serialize_dedup_document(document) async for document in cursor]

    async def list_cluster_documents(self, status: str = "open", limit: int = 100) -> list[dict[str, Any]]:
        cursor = self.clusters.find({"status": status}).sort("score", DESCENDING).limit(limit)
        return [serialize_dedup_document(document) async for document in cursor]

    async def get_cluster_document(self, cluster_id: ObjectId) -> dict[str, Any] | None:
        document = await self.clusters.find_one({"_id": cluster_id})
        return serialize_dedup_document(document) if document else None

    async def get_leads_by_ids(self, lead_ids: list[ObjectId]) -> list[dict[str, Any]]:
        cursor = self.leads.find({"_id": {"$in": lead_ids}})
        documents = [document async for document in cursor]
        order = {str(lead_id): index for index, lead_id in enumerate(lead_ids)}
        documents.sort(key=lambda document: order.get(str(document["_id"]), 999))
        return documents

    async def list_active_leads(self, limit: int = 1000) -> list[dict[str, Any]]:
        cursor = self.leads.find({"isActive": {"$ne": False}, "isDiscarded": {"$ne": True}}).limit(limit)
        return [document async for document in cursor]

    async def get_suppressed_pairs(self) -> set[tuple[str, str]]:
        cursor = self.candidates.find({"status": {"$in": ["ignored", "distinct"]}}, {"leadIds": 1})
        pairs: set[tuple[str, str]] = set()
        async for document in cursor:
            lead_ids = sorted(str(value) for value in document.get("leadIds", []))
            if len(lead_ids) == 2:
                pairs.add((lead_ids[0], lead_ids[1]))
        return pairs

    async def replace_open_candidates_and_clusters(
        self,
        candidates: list[dict[str, Any]],
        clusters: list[dict[str, Any]],
    ) -> tuple[int, int]:
        await self.candidates.delete_many({"status": "open"})
        await self.clusters.delete_many({"status": "open"})
        if clusters:
            await self.clusters.insert_many(clusters)
        if candidates:
            await self.candidates.insert_many(candidates)
        return len(candidates), len(clusters)

    async def mark_cluster(self, cluster_id: ObjectId, status: str) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        await self.clusters.update_one({"_id": cluster_id}, {"$set": {"status": status, "updatedAt": now}})
        await self.candidates.update_many({"clusterId": cluster_id}, {"$set": {"status": status, "updatedAt": now}})
        return await self.get_cluster_document(cluster_id)

    async def merge_cluster(
        self,
        *,
        cluster_id: ObjectId,
        primary_lead_id: ObjectId,
        merged_lead_ids: list[ObjectId],
        performed_by: str,
        reason: str | None,
    ) -> dict[str, Any]:
        primary = await self.leads.find_one({"_id": primary_lead_id})
        duplicates = [document async for document in self.leads.find({"_id": {"$in": merged_lead_ids}})]
        now = datetime.now(UTC)
        merged_fields: dict[str, Any] = {}
        set_data: dict[str, Any] = {"updatedAt": now}
        fillable_fields = [
            "website",
            "instagram",
            "phone",
            "email",
            "address",
            "city",
            "district",
            "countryCode",
        ]
        for field in fillable_fields:
            if primary and primary.get(field):
                continue
            value = next((duplicate.get(field) for duplicate in duplicates if duplicate.get(field)), None)
            if value:
                set_data[field] = value
                merged_fields[field] = value
        for score_field in ("priorityScore", "fitScore", "confidence"):
            values = [int(primary.get(score_field) or 0)] if primary else []
            values.extend(int(duplicate.get(score_field) or 0) for duplicate in duplicates)
            if values:
                set_data[score_field] = max(values)

        await self.leads.update_one({"_id": primary_lead_id}, {"$set": set_data})
        await self.leads.update_many(
            {"_id": {"$in": merged_lead_ids}},
            {
                "$set": {
                    "isActive": False,
                    "isDiscarded": True,
                    "mergedIntoLeadId": primary_lead_id,
                    "mergeReason": reason,
                    "updatedAt": now,
                }
            },
        )
        await self.sources.update_many({"leadId": {"$in": merged_lead_ids}}, {"$set": {"leadId": primary_lead_id}})
        await self.activities.update_many({"leadId": {"$in": merged_lead_ids}}, {"$set": {"leadId": primary_lead_id}})
        await self.clusters.update_one(
            {"_id": cluster_id},
            {
                "$set": {
                    "status": "merged",
                    "mergedIntoLeadId": primary_lead_id,
                    "updatedAt": now,
                }
            },
        )
        await self.candidates.update_many(
            {"clusterId": cluster_id},
            {"$set": {"status": "merged", "updatedAt": now}},
        )
        event = {
            "clusterId": cluster_id,
            "primaryLeadId": primary_lead_id,
            "mergedLeadIds": merged_lead_ids,
            "mergedFields": merged_fields,
            "performedBy": performed_by,
            "reason": reason,
            "createdAt": now,
        }
        result = await self.merge_events.insert_one(event)
        created = await self.merge_events.find_one({"_id": result.inserted_id})
        return serialize_dedup_document(created)
