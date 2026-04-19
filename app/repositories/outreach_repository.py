from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING

from app.core.object_id import object_id_to_str
from app.repositories.lead_repository import serialize_document


ID_FIELDS = {"campaignId", "leadId", "draftId", "outboxMessageId"}


def serialize_outreach_document(document: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(document)
    serialized["id"] = object_id_to_str(serialized.pop("_id", None))
    for key in ID_FIELDS:
        if key in serialized and serialized[key] is not None:
            serialized[key] = object_id_to_str(serialized[key])
    return serialized


class OutreachRepository:
    def __init__(self, database: AsyncIOMotorDatabase):
        self.leads = database.leads
        self.activities = database.lead_activities
        self.campaigns = database.campaigns
        self.targets = database.campaign_targets
        self.drafts = database.message_drafts
        self.events = database.campaign_events
        self.outbox = database.outbox_messages
        self.attempts = database.send_attempts
        self.suppressions = database.suppression_list
        self.delivery_events = database.delivery_events

    async def get_campaign(self, campaign_id: ObjectId) -> dict[str, Any] | None:
        return await self.campaigns.find_one({"_id": campaign_id})

    async def get_draft(self, draft_id: ObjectId) -> dict[str, Any] | None:
        document = await self.drafts.find_one({"_id": draft_id})
        return serialize_outreach_document(document) if document else None

    async def list_approved_drafts(self, campaign_id: ObjectId, limit: int = 250) -> list[dict[str, Any]]:
        cursor = (
            self.drafts.find({"campaignId": campaign_id, "draftStatus": "approved", "channel": "email"})
            .sort("updatedAt", DESCENDING)
            .limit(limit)
        )
        return [serialize_outreach_document(document) async for document in cursor]

    async def get_lead(self, lead_id: ObjectId) -> dict[str, Any] | None:
        document = await self.leads.find_one({"_id": lead_id})
        return serialize_document(document) if document else None

    async def get_leads_by_ids(self, lead_ids: list[ObjectId]) -> dict[str, dict[str, Any]]:
        if not lead_ids:
            return {}
        cursor = self.leads.find({"_id": {"$in": lead_ids}})
        leads = [serialize_document(document) async for document in cursor]
        return {lead["id"]: lead for lead in leads}

    async def get_outbox_by_draft(self, draft_id: ObjectId) -> dict[str, Any] | None:
        document = await self.outbox.find_one({"draftId": draft_id})
        return serialize_outreach_document(document) if document else None

    async def create_or_update_outbox_message(
        self,
        *,
        campaign_id: ObjectId,
        lead_id: ObjectId,
        draft_id: ObjectId,
        document: dict[str, Any],
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        await self.outbox.update_one(
            {"draftId": draft_id},
            {
                "$setOnInsert": {
                    "campaignId": campaign_id,
                    "leadId": lead_id,
                    "draftId": draft_id,
                    "createdAt": now,
                    "attemptCount": 0,
                    "sentAt": None,
                },
                "$set": {**document, "updatedAt": now},
            },
            upsert=True,
        )
        created = await self.outbox.find_one({"draftId": draft_id})
        return serialize_outreach_document(created)

    async def get_outbox(self, outbox_id: ObjectId) -> dict[str, Any] | None:
        document = await self.outbox.find_one({"_id": outbox_id})
        return serialize_outreach_document(document) if document else None

    async def list_outbox(
        self,
        *,
        campaign_id: ObjectId | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}
        if campaign_id:
            query["campaignId"] = campaign_id
        if status:
            query["status"] = status
        cursor = self.outbox.find(query).sort("updatedAt", DESCENDING).limit(limit)
        return [serialize_outreach_document(document) async for document in cursor]

    async def update_outbox(self, outbox_id: ObjectId, update_data: dict[str, Any]) -> dict[str, Any] | None:
        update_data["updatedAt"] = datetime.now(UTC)
        await self.outbox.update_one({"_id": outbox_id}, {"$set": update_data})
        return await self.get_outbox(outbox_id)

    async def create_send_attempt(
        self,
        *,
        outbox_message_id: ObjectId,
        attempt_number: int,
        provider: str,
        status: str,
        response_metadata: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        document = {
            "outboxMessageId": outbox_message_id,
            "attemptNumber": attempt_number,
            "provider": provider,
            "status": status,
            "responseMetadata": response_metadata or {},
            "errorMessage": error_message,
            "createdAt": datetime.now(UTC),
        }
        result = await self.attempts.insert_one(document)
        created = await self.attempts.find_one({"_id": result.inserted_id})
        return serialize_outreach_document(created)

    async def list_send_attempts(self, outbox_message_id: ObjectId, limit: int = 20) -> list[dict[str, Any]]:
        cursor = (
            self.attempts.find({"outboxMessageId": outbox_message_id})
            .sort("createdAt", DESCENDING)
            .limit(limit)
        )
        return [serialize_outreach_document(document) async for document in cursor]

    async def create_delivery_event(
        self,
        *,
        outbox_message_id: ObjectId,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        document = {
            "outboxMessageId": outbox_message_id,
            "eventType": event_type,
            "payload": payload,
            "createdAt": datetime.now(UTC),
        }
        result = await self.delivery_events.insert_one(document)
        created = await self.delivery_events.find_one({"_id": result.inserted_id})
        return serialize_outreach_document(created)

    async def list_delivery_events(self, outbox_message_id: ObjectId, limit: int = 50) -> list[dict[str, Any]]:
        cursor = (
            self.delivery_events.find({"outboxMessageId": outbox_message_id})
            .sort("createdAt", DESCENDING)
            .limit(limit)
        )
        return [serialize_outreach_document(document) async for document in cursor]

    async def create_campaign_event(
        self,
        *,
        campaign_id: ObjectId,
        event_type: str,
        payload: dict[str, Any],
        lead_id: ObjectId | None = None,
    ) -> None:
        await self.events.insert_one(
            {
                "campaignId": campaign_id,
                "leadId": lead_id,
                "eventType": event_type,
                "payload": payload,
                "createdAt": datetime.now(UTC),
            }
        )

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

    async def update_target_status(self, campaign_id: ObjectId, lead_id: ObjectId, target_status: str) -> None:
        await self.targets.update_one(
            {"campaignId": campaign_id, "leadId": lead_id},
            {"$set": {"targetStatus": target_status}},
        )

    async def list_suppressions(self, limit: int = 250) -> list[dict[str, Any]]:
        cursor = self.suppressions.find({}).sort("createdAt", DESCENDING).limit(limit)
        return [serialize_outreach_document(document) async for document in cursor]

    async def create_suppression(self, document: dict[str, Any]) -> dict[str, Any]:
        document["createdAt"] = datetime.now(UTC)
        await self.suppressions.update_one(
            {"identityType": document["identityType"], "identityValue": document["identityValue"]},
            {"$set": document},
            upsert=True,
        )
        created = await self.suppressions.find_one(
            {"identityType": document["identityType"], "identityValue": document["identityValue"]}
        )
        return serialize_outreach_document(created)

    async def delete_suppression(self, suppression_id: ObjectId) -> bool:
        result = await self.suppressions.delete_one({"_id": suppression_id})
        return result.deleted_count > 0

    async def find_suppression(self, email: str | None) -> dict[str, Any] | None:
        if not email:
            return None
        value = email.strip().lower()
        domain = value.split("@", 1)[1] if "@" in value else ""
        query = {
            "$or": [
                {"identityType": "email", "identityValue": value},
                {"identityType": "domain", "identityValue": domain},
            ]
        }
        document = await self.suppressions.find_one(query)
        return serialize_outreach_document(document) if document else None
