import math
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from app.core.object_id import object_id_to_str
from app.schemas.lead import LeadActivityCreate, LeadCreate, LeadUpdate, SortDirection

LEAD_SORT_FIELDS = {
    "name",
    "city",
    "district",
    "pipelineStatus",
    "priorityScore",
    "fitScore",
    "confidence",
    "createdAt",
    "updatedAt",
}


def normalize_lead_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(normalized.lower().strip().split())


def serialize_document(document: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(document)
    serialized["id"] = object_id_to_str(serialized.pop("_id", None))
    if "leadId" in serialized:
        serialized["leadId"] = object_id_to_str(serialized["leadId"])
    return serialized


class LeadRepository:
    def __init__(self, database: AsyncIOMotorDatabase):
        self.database = database
        self.leads = database.leads
        self.sources = database.lead_sources
        self.activities = database.lead_activities

    async def list_leads(
        self,
        *,
        q: str | None,
        pipeline_status: str | None,
        city: str | None,
        district: str | None,
        min_priority_score: int | None,
        max_priority_score: int | None,
        page: int,
        page_size: int,
        sort_by: str,
        sort_direction: SortDirection,
    ) -> tuple[list[dict[str, Any]], int]:
        query: dict[str, Any] = {}
        if q:
            pattern = re.escape(q.strip())
            query["$or"] = [
                {"name": {"$regex": pattern, "$options": "i"}},
                {"normalizedName": {"$regex": pattern, "$options": "i"}},
                {"city": {"$regex": pattern, "$options": "i"}},
                {"district": {"$regex": pattern, "$options": "i"}},
            ]
        if pipeline_status:
            query["pipelineStatus"] = pipeline_status
        if city:
            query["city"] = {"$regex": f"^{re.escape(city.strip())}$", "$options": "i"}
        if district:
            query["district"] = {"$regex": f"^{re.escape(district.strip())}$", "$options": "i"}
        if min_priority_score is not None or max_priority_score is not None:
            score_filter: dict[str, int] = {}
            if min_priority_score is not None:
                score_filter["$gte"] = min_priority_score
            if max_priority_score is not None:
                score_filter["$lte"] = max_priority_score
            query["priorityScore"] = score_filter

        safe_sort_by = sort_by if sort_by in LEAD_SORT_FIELDS else "updatedAt"
        sort_order = ASCENDING if sort_direction == SortDirection.ASC else DESCENDING
        skip = (page - 1) * page_size
        total = await self.leads.count_documents(query)
        cursor = self.leads.find(query).sort(safe_sort_by, sort_order).skip(skip).limit(page_size)
        items = [serialize_document(document) async for document in cursor]
        return items, total

    async def create_lead(self, payload: LeadCreate) -> dict[str, Any]:
        now = datetime.now(UTC)
        document = payload.model_dump()
        document["schemaVersion"] = 1
        document["normalizedName"] = document["normalizedName"] or normalize_lead_name(document["name"])
        document["createdAt"] = now
        document["updatedAt"] = now
        result = await self.leads.insert_one(document)
        created = await self.leads.find_one({"_id": result.inserted_id})
        return serialize_document(created)

    async def get_lead(self, lead_id: ObjectId) -> dict[str, Any] | None:
        document = await self.leads.find_one({"_id": lead_id})
        return serialize_document(document) if document else None

    async def get_by_normalized_name(self, normalized_name: str) -> dict[str, Any] | None:
        document = await self.leads.find_one({"normalizedName": normalized_name})
        return serialize_document(document) if document else None

    async def update_lead(self, lead_id: ObjectId, payload: LeadUpdate) -> dict[str, Any] | None:
        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            return await self.get_lead(lead_id)
        if update_data.get("name") and not update_data.get("normalizedName"):
            update_data["normalizedName"] = normalize_lead_name(update_data["name"])
        update_data["updatedAt"] = datetime.now(UTC)
        await self.leads.update_one({"_id": lead_id}, {"$set": update_data})
        return await self.get_lead(lead_id)

    async def list_sources(self, lead_id: ObjectId) -> list[dict[str, Any]]:
        cursor = self.sources.find({"leadId": lead_id}).sort("capturedAt", DESCENDING)
        return [serialize_document(document) async for document in cursor]

    async def create_source(
        self,
        *,
        lead_id: ObjectId,
        source_type: str,
        external_id: str | None,
        source_url: str | None,
        raw_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        document = {
            "leadId": lead_id,
            "sourceType": source_type,
            "externalId": external_id,
            "sourceUrl": source_url,
            "capturedAt": now,
            "rawMetadata": raw_metadata,
        }
        result = await self.sources.insert_one(document)
        created = await self.sources.find_one({"_id": result.inserted_id})
        return serialize_document(created)

    async def list_activity(self, lead_id: ObjectId) -> list[dict[str, Any]]:
        cursor = self.activities.find({"leadId": lead_id}).sort("createdAt", DESCENDING)
        return [serialize_document(document) async for document in cursor]

    async def create_activity(
        self,
        lead_id: ObjectId,
        payload: LeadActivityCreate,
        performed_by: str,
    ) -> dict[str, Any]:
        document = payload.model_dump()
        document["leadId"] = lead_id
        document["performedBy"] = performed_by
        document["createdAt"] = datetime.now(UTC)
        result = await self.activities.insert_one(document)
        await self.leads.update_one({"_id": lead_id}, {"$set": {"updatedAt": datetime.now(UTC)}})
        created = await self.activities.find_one({"_id": result.inserted_id})
        return serialize_document(created)


def calculate_total_pages(total: int, page_size: int) -> int:
    return max(1, math.ceil(total / page_size))
