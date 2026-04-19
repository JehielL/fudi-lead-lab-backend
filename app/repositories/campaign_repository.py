import re
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING

from app.core.object_id import object_id_to_str
from app.repositories.lead_repository import serialize_document
from app.schemas.campaigns import CampaignTargetCriteria


ID_FIELDS = {"campaignId", "leadId", "templateId"}


def serialize_campaign_document(document: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(document)
    serialized["id"] = object_id_to_str(serialized.pop("_id", None))
    for key in ID_FIELDS:
        if key in serialized and serialized[key] is not None:
            serialized[key] = object_id_to_str(serialized[key])
    return serialized


class CampaignRepository:
    def __init__(self, database: AsyncIOMotorDatabase):
        self.leads = database.leads
        self.feature_snapshots = database.feature_snapshots
        self.activities = database.lead_activities
        self.campaigns = database.campaigns
        self.targets = database.campaign_targets
        self.templates = database.message_templates
        self.drafts = database.message_drafts
        self.events = database.campaign_events

    async def list_campaigns(self, limit: int = 100) -> list[dict[str, Any]]:
        cursor = self.campaigns.find({}).sort("updatedAt", DESCENDING).limit(limit)
        return [serialize_campaign_document(document) async for document in cursor]

    async def create_campaign(self, document: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC)
        document["createdAt"] = now
        document["updatedAt"] = now
        result = await self.campaigns.insert_one(document)
        created = await self.campaigns.find_one({"_id": result.inserted_id})
        return serialize_campaign_document(created)

    async def get_campaign(self, campaign_id: ObjectId) -> dict[str, Any] | None:
        document = await self.campaigns.find_one({"_id": campaign_id})
        return serialize_campaign_document(document) if document else None

    async def update_campaign(self, campaign_id: ObjectId, update_data: dict[str, Any]) -> dict[str, Any] | None:
        if update_data:
            update_data["updatedAt"] = datetime.now(UTC)
            await self.campaigns.update_one({"_id": campaign_id}, {"$set": update_data})
        return await self.get_campaign(campaign_id)

    async def list_selectable_leads(self, criteria: CampaignTargetCriteria) -> list[dict[str, Any]]:
        query: dict[str, Any] = {
            "isActive": {"$ne": False},
            "isDiscarded": {"$ne": True},
        }
        if criteria.pipelineStatus:
            query["pipelineStatus"] = criteria.pipelineStatus.value
        elif criteria.minPriorityScore is not None:
            query["$or"] = [
                {"priorityScore": {"$gte": criteria.minPriorityScore}},
                {"pipelineStatus": {"$in": ["QUALIFIED", "CONTACTED", "CONVERTED"]}},
            ]
        if criteria.city:
            query["city"] = {"$regex": f"^{re.escape(criteria.city.strip())}$", "$options": "i"}
        if criteria.district:
            query["district"] = {"$regex": f"^{re.escape(criteria.district.strip())}$", "$options": "i"}
        if criteria.modelScored is not None:
            query["modelScored"] = criteria.modelScored
        if criteria.enrichmentAvailable is True:
            query["$or"] = [
                {"lastEnrichedAt": {"$ne": None}},
                {"enrichmentStatus": "completed"},
            ]
        elif criteria.enrichmentAvailable is False:
            query["lastEnrichedAt"] = None

        cursor = self.leads.find(query).sort("priorityScore", DESCENDING).limit(criteria.limit)
        return [serialize_document(document) async for document in cursor]

    async def upsert_target(
        self,
        *,
        campaign_id: ObjectId,
        lead_id: ObjectId,
        document: dict[str, Any],
    ) -> dict[str, Any]:
        await self.targets.update_one(
            {"campaignId": campaign_id, "leadId": lead_id},
            {
                "$setOnInsert": {
                    "campaignId": campaign_id,
                    "leadId": lead_id,
                    "includedAt": datetime.now(UTC),
                },
                "$set": document,
            },
            upsert=True,
        )
        target = await self.targets.find_one({"campaignId": campaign_id, "leadId": lead_id})
        return serialize_campaign_document(target)

    async def list_targets(self, campaign_id: ObjectId, limit: int = 250) -> list[dict[str, Any]]:
        cursor = self.targets.find({"campaignId": campaign_id}).sort("includedAt", DESCENDING).limit(limit)
        return [serialize_campaign_document(document) async for document in cursor]

    async def update_target_status(
        self,
        *,
        campaign_id: ObjectId,
        lead_id: ObjectId,
        target_status: str,
    ) -> None:
        await self.targets.update_one(
            {"campaignId": campaign_id, "leadId": lead_id},
            {"$set": {"targetStatus": target_status}},
        )

    async def get_lead(self, lead_id: ObjectId) -> dict[str, Any] | None:
        document = await self.leads.find_one({"_id": lead_id})
        return serialize_document(document) if document else None

    async def get_leads_by_ids(self, lead_ids: list[ObjectId]) -> dict[str, dict[str, Any]]:
        if not lead_ids:
            return {}
        cursor = self.leads.find({"_id": {"$in": lead_ids}})
        leads = [serialize_document(document) async for document in cursor]
        return {lead["id"]: lead for lead in leads}

    async def get_latest_feature_snapshot(self, lead_id: ObjectId) -> dict[str, Any] | None:
        document = await self.feature_snapshots.find_one({"leadId": lead_id}, sort=[("createdAt", DESCENDING)])
        if not document:
            return None
        serialized = serialize_campaign_document(document)
        if "sourceSnapshotIds" in serialized:
            serialized["sourceSnapshotIds"] = [object_id_to_str(value) for value in document.get("sourceSnapshotIds", [])]
        return serialized

    async def list_templates(self, channel: str | None = None) -> list[dict[str, Any]]:
        query = {"channel": channel} if channel else {}
        cursor = self.templates.find(query).sort("updatedAt", DESCENDING)
        return [serialize_campaign_document(document) async for document in cursor]

    async def create_template(self, document: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC)
        document["createdAt"] = now
        document["updatedAt"] = now
        result = await self.templates.insert_one(document)
        created = await self.templates.find_one({"_id": result.inserted_id})
        return serialize_campaign_document(created)

    async def get_template(self, template_id: ObjectId) -> dict[str, Any] | None:
        document = await self.templates.find_one({"_id": template_id})
        return serialize_campaign_document(document) if document else None

    async def get_default_template(self, channel: str) -> dict[str, Any] | None:
        document = await self.templates.find_one(
            {"channel": channel, "isActive": True},
            sort=[("updatedAt", DESCENDING)],
        )
        return serialize_campaign_document(document) if document else None

    async def list_drafts(self, campaign_id: ObjectId, limit: int = 250) -> list[dict[str, Any]]:
        cursor = self.drafts.find({"campaignId": campaign_id}).sort("updatedAt", DESCENDING).limit(limit)
        return [serialize_campaign_document(document) async for document in cursor]

    async def create_or_update_draft(
        self,
        *,
        campaign_id: ObjectId,
        lead_id: ObjectId,
        template_id: ObjectId,
        document: dict[str, Any],
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        await self.drafts.update_one(
            {"campaignId": campaign_id, "leadId": lead_id, "templateId": template_id},
            {
                "$setOnInsert": {
                    "campaignId": campaign_id,
                    "leadId": lead_id,
                    "templateId": template_id,
                    "createdAt": now,
                },
                "$set": {**document, "updatedAt": now},
            },
            upsert=True,
        )
        draft = await self.drafts.find_one({"campaignId": campaign_id, "leadId": lead_id, "templateId": template_id})
        return serialize_campaign_document(draft)

    async def get_draft(self, draft_id: ObjectId) -> dict[str, Any] | None:
        document = await self.drafts.find_one({"_id": draft_id})
        return serialize_campaign_document(document) if document else None

    async def update_draft(self, draft_id: ObjectId, update_data: dict[str, Any]) -> dict[str, Any] | None:
        if update_data:
            update_data["updatedAt"] = datetime.now(UTC)
            await self.drafts.update_one({"_id": draft_id}, {"$set": update_data})
        return await self.get_draft(draft_id)

    async def create_event(
        self,
        *,
        campaign_id: ObjectId,
        event_type: str,
        payload: dict[str, Any],
        lead_id: ObjectId | None = None,
    ) -> dict[str, Any]:
        document = {
            "campaignId": campaign_id,
            "leadId": lead_id,
            "eventType": event_type,
            "payload": payload,
            "createdAt": datetime.now(UTC),
        }
        result = await self.events.insert_one(document)
        created = await self.events.find_one({"_id": result.inserted_id})
        return serialize_campaign_document(created)

    async def list_events(self, campaign_id: ObjectId, limit: int = 100) -> list[dict[str, Any]]:
        cursor = self.events.find({"campaignId": campaign_id}).sort("createdAt", DESCENDING).limit(limit)
        return [serialize_campaign_document(document) async for document in cursor]

    async def create_lead_activity(
        self,
        *,
        lead_id: ObjectId,
        activity_type: str,
        channel: str,
        description: str,
        performed_by: str,
    ) -> None:
        now = datetime.now(UTC)
        await self.activities.insert_one(
            {
                "leadId": lead_id,
                "activityType": activity_type,
                "channel": channel,
                "description": description,
                "performedBy": performed_by,
                "createdAt": now,
            }
        )
        await self.leads.update_one({"_id": lead_id}, {"$set": {"updatedAt": now}})
