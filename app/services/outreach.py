from datetime import UTC, datetime
from typing import Annotated

from bson import ObjectId
from fastapi import Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import Settings, get_settings
from app.core.object_id import parse_object_id
from app.db.dependencies import get_database
from app.repositories.outreach_repository import OutreachRepository
from app.schemas.auth import UserResponse
from app.schemas.outreach import (
    CampaignSendResponse,
    OutboxDetail,
    OutboxMessage,
    OutboxStatus,
    QueueDraftRequest,
    ScheduleCampaignRequest,
    SendAttempt,
    SuppressionCreate,
    SuppressionEntry,
)
from app.services.outreach_providers import OutreachProvider, SmtpOutreachProvider


class OutreachService:
    def __init__(
        self,
        repository: OutreachRepository,
        provider: OutreachProvider,
        settings: Settings,
    ):
        self.repository = repository
        self.provider = provider
        self.settings = settings

    async def queue_draft(
        self,
        draft_id: str,
        payload: QueueDraftRequest,
        current_user: UserResponse,
    ) -> OutboxMessage:
        draft = await self._get_draft(draft_id)
        if draft["draftStatus"] != "approved":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only approved drafts can be queued.",
            )
        if draft["channel"] != "email":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only email drafts can be queued in this phase.",
            )
        campaign_id = parse_object_id(draft["campaignId"])
        lead_id = parse_object_id(draft["leadId"])
        lead = await self.repository.get_lead(lead_id)
        if lead is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

        recipient = (lead.get("email") or "").strip().lower() or None
        suppression = await self.repository.find_suppression(recipient)
        outbox_status = OutboxStatus.QUEUED
        last_error = None
        if not recipient:
            outbox_status = OutboxStatus.SUPPRESSED
            last_error = "Lead has no email recipient."
        elif suppression:
            outbox_status = OutboxStatus.SUPPRESSED
            last_error = f"Recipient suppressed: {suppression['reason']}"

        message = await self.repository.create_or_update_outbox_message(
            campaign_id=campaign_id,
            lead_id=lead_id,
            draft_id=parse_object_id(draft_id),
            document={
                "channel": "email",
                "to": recipient,
                "subject": draft.get("subject"),
                "body": draft["body"],
                "status": outbox_status.value,
                "scheduledAt": payload.scheduledAt,
                "lastError": last_error,
            },
        )
        await self.repository.create_campaign_event(
            campaign_id=campaign_id,
            lead_id=lead_id,
            event_type="outbox_queued" if outbox_status == OutboxStatus.QUEUED else "outbox_suppressed",
            payload={"draftId": draft_id, "outboxMessageId": message["id"], "queuedBy": current_user.username},
        )
        await self.repository.create_lead_activity(
            lead_id=lead_id,
            activity_type="outbox_queued" if outbox_status == OutboxStatus.QUEUED else "outbox_suppressed",
            channel="email",
            description=last_error or "Approved campaign draft queued for outreach execution.",
            performed_by=current_user.username,
        )
        return await self._hydrate_outbox_message(message)

    async def send_draft(self, draft_id: str, current_user: UserResponse) -> OutboxMessage:
        message = await self.queue_draft(draft_id, QueueDraftRequest(), current_user)
        if message.status != OutboxStatus.QUEUED:
            return message
        return await self.send_outbox_message(message.id, current_user, retry=False)

    async def send_campaign(self, campaign_id: str, current_user: UserResponse) -> CampaignSendResponse:
        object_id = parse_object_id(campaign_id)
        await self._ensure_campaign(object_id)
        drafts = await self.repository.list_approved_drafts(object_id)
        response = CampaignSendResponse(campaignId=campaign_id)
        for draft in drafts:
            message = await self.send_draft(draft["id"], current_user)
            response.messages.append(message)
            if message.status == OutboxStatus.SENT:
                response.sentCount += 1
            elif message.status == OutboxStatus.SUPPRESSED:
                response.suppressedCount += 1
            elif message.status == OutboxStatus.FAILED:
                response.failedCount += 1
            elif message.status == OutboxStatus.QUEUED:
                response.queuedCount += 1
        await self.repository.create_campaign_event(
            campaign_id=object_id,
            event_type="campaign_send_requested",
            payload={
                "requestedBy": current_user.username,
                "sentCount": response.sentCount,
                "failedCount": response.failedCount,
                "suppressedCount": response.suppressedCount,
            },
        )
        return response

    async def schedule_campaign(
        self,
        campaign_id: str,
        payload: ScheduleCampaignRequest,
        current_user: UserResponse,
    ) -> CampaignSendResponse:
        object_id = parse_object_id(campaign_id)
        await self._ensure_campaign(object_id)
        drafts = await self.repository.list_approved_drafts(object_id)
        response = CampaignSendResponse(campaignId=campaign_id)
        for draft in drafts:
            message = await self.queue_draft(draft["id"], QueueDraftRequest(scheduledAt=payload.scheduledAt), current_user)
            response.messages.append(message)
            if message.status == OutboxStatus.SUPPRESSED:
                response.suppressedCount += 1
            else:
                response.queuedCount += 1
        await self.repository.create_campaign_event(
            campaign_id=object_id,
            event_type="campaign_scheduled",
            payload={"scheduledAt": payload.scheduledAt.isoformat() if payload.scheduledAt else None},
        )
        return response

    async def list_campaign_outbox(self, campaign_id: str) -> list[OutboxMessage]:
        object_id = parse_object_id(campaign_id)
        await self._ensure_campaign(object_id)
        messages = await self.repository.list_outbox(campaign_id=object_id)
        return [await self._hydrate_outbox_message(message) for message in messages]

    async def list_outbox(self, outbox_status: OutboxStatus | None = None) -> list[OutboxMessage]:
        messages = await self.repository.list_outbox(status=outbox_status.value if outbox_status else None)
        return [await self._hydrate_outbox_message(message) for message in messages]

    async def get_outbox_detail(self, outbox_id: str) -> OutboxDetail:
        object_id = parse_object_id(outbox_id)
        message = await self._get_outbox(object_id)
        attempts = await self.repository.list_send_attempts(object_id)
        events = await self.repository.list_delivery_events(object_id)
        return OutboxDetail(
            message=await self._hydrate_outbox_message(message),
            attempts=[SendAttempt.model_validate(attempt) for attempt in attempts],
            events=events,
        )

    async def retry_outbox(self, outbox_id: str, current_user: UserResponse) -> OutboxMessage:
        return await self.send_outbox_message(outbox_id, current_user, retry=True)

    async def cancel_outbox(self, outbox_id: str, current_user: UserResponse) -> OutboxMessage:
        object_id = parse_object_id(outbox_id)
        message = await self._get_outbox(object_id)
        if message["status"] == OutboxStatus.SENT.value:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Sent messages cannot be cancelled.")
        updated = await self.repository.update_outbox(
            object_id,
            {
                "status": OutboxStatus.CANCELLED.value,
                "lastError": None,
            },
        )
        campaign_id = parse_object_id(updated["campaignId"])
        lead_id = parse_object_id(updated["leadId"])
        await self.repository.create_campaign_event(
            campaign_id=campaign_id,
            lead_id=lead_id,
            event_type="outbox_cancelled",
            payload={"outboxMessageId": outbox_id, "cancelledBy": current_user.username},
        )
        await self.repository.create_lead_activity(
            lead_id=lead_id,
            activity_type="outbox_cancelled",
            channel="email",
            description="Queued outreach message cancelled.",
            performed_by=current_user.username,
        )
        return await self._hydrate_outbox_message(updated)

    async def send_outbox_message(
        self,
        outbox_id: str,
        current_user: UserResponse,
        *,
        retry: bool,
    ) -> OutboxMessage:
        object_id = parse_object_id(outbox_id)
        message = await self._get_outbox(object_id)
        if message["status"] in {OutboxStatus.CANCELLED.value, OutboxStatus.SUPPRESSED.value, OutboxStatus.SENT.value}:
            return await self._hydrate_outbox_message(message)
        if retry and int(message.get("attemptCount") or 0) >= self.settings.outreach_max_attempts:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Maximum send attempts reached.")

        suppression = await self.repository.find_suppression(message.get("to"))
        if suppression:
            updated = await self.repository.update_outbox(
                object_id,
                {"status": OutboxStatus.SUPPRESSED.value, "lastError": f"Recipient suppressed: {suppression['reason']}"},
            )
            return await self._hydrate_outbox_message(updated)

        attempt_number = int(message.get("attemptCount") or 0) + 1
        await self.repository.update_outbox(
            object_id,
            {"status": OutboxStatus.SENDING.value, "attemptCount": attempt_number},
        )
        outbox_model = OutboxMessage.model_validate({**message, "attemptCount": attempt_number, "status": OutboxStatus.SENDING.value})
        campaign_id = parse_object_id(message["campaignId"])
        lead_id = parse_object_id(message["leadId"])
        try:
            result = await self.provider.send(outbox_model)
            updated = await self.repository.update_outbox(
                object_id,
                {
                    "status": OutboxStatus.SENT.value,
                    "sentAt": datetime.now(UTC),
                    "lastError": None,
                },
            )
            await self.repository.create_send_attempt(
                outbox_message_id=object_id,
                attempt_number=attempt_number,
                provider=result.provider,
                status=OutboxStatus.SENT.value,
                response_metadata=result.metadata,
            )
            await self.repository.create_delivery_event(
                outbox_message_id=object_id,
                event_type="sent",
                payload={"provider": result.provider, **result.metadata},
            )
            await self.repository.create_campaign_event(
                campaign_id=campaign_id,
                lead_id=lead_id,
                event_type="outbox_sent",
                payload={"outboxMessageId": outbox_id, "sentBy": current_user.username},
            )
            await self.repository.create_lead_activity(
                lead_id=lead_id,
                activity_type="outreach_sent",
                channel="email",
                description="Campaign outreach email sent.",
                performed_by=current_user.username,
            )
            await self.repository.update_target_status(campaign_id, lead_id, "sent")
            return await self._hydrate_outbox_message(updated)
        except Exception as exc:
            error_message = str(exc)[:500]
            updated = await self.repository.update_outbox(
                object_id,
                {
                    "status": OutboxStatus.FAILED.value,
                    "lastError": error_message,
                },
            )
            await self.repository.create_send_attempt(
                outbox_message_id=object_id,
                attempt_number=attempt_number,
                provider=self.provider.name,
                status=OutboxStatus.FAILED.value,
                error_message=error_message,
            )
            await self.repository.create_delivery_event(
                outbox_message_id=object_id,
                event_type="failed",
                payload={"error": error_message},
            )
            await self.repository.create_campaign_event(
                campaign_id=campaign_id,
                lead_id=lead_id,
                event_type="outbox_failed",
                payload={"outboxMessageId": outbox_id, "error": error_message},
            )
            await self.repository.create_lead_activity(
                lead_id=lead_id,
                activity_type="outreach_failed",
                channel="email",
                description=f"Campaign outreach email failed: {error_message}",
                performed_by=current_user.username,
            )
            return await self._hydrate_outbox_message(updated)

    async def list_suppressions(self) -> list[SuppressionEntry]:
        suppressions = await self.repository.list_suppressions()
        return [SuppressionEntry.model_validate(item) for item in suppressions]

    async def create_suppression(self, payload: SuppressionCreate) -> SuppressionEntry:
        document = payload.model_dump()
        document["identityValue"] = document["identityValue"].strip().lower()
        suppression = await self.repository.create_suppression(document)
        return SuppressionEntry.model_validate(suppression)

    async def delete_suppression(self, suppression_id: str) -> None:
        deleted = await self.repository.delete_suppression(parse_object_id(suppression_id))
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suppression not found")

    async def _ensure_campaign(self, campaign_id: ObjectId) -> None:
        campaign = await self.repository.get_campaign(campaign_id)
        if campaign is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    async def _get_draft(self, draft_id: str) -> dict:
        draft = await self.repository.get_draft(parse_object_id(draft_id))
        if draft is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
        return draft

    async def _get_outbox(self, outbox_id: ObjectId) -> dict:
        message = await self.repository.get_outbox(outbox_id)
        if message is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outbox message not found")
        return message

    async def _hydrate_outbox_message(self, message: dict) -> OutboxMessage:
        lead = await self.repository.get_lead(parse_object_id(message["leadId"]))
        message["lead"] = lead
        return OutboxMessage.model_validate(message)


def get_outreach_service(
    database: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OutreachService:
    return OutreachService(
        OutreachRepository(database),
        SmtpOutreachProvider(settings),
        settings,
    )
