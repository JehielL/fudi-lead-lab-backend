from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.lead import LeadSummary


class OutboxStatus(StrEnum):
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUPPRESSED = "suppressed"


class SuppressionIdentityType(StrEnum):
    EMAIL = "email"
    DOMAIN = "domain"


class SuppressionCreate(BaseModel):
    identityType: SuppressionIdentityType
    identityValue: str = Field(min_length=1, max_length=320)
    reason: str = Field(min_length=1, max_length=500)


class SuppressionEntry(SuppressionCreate):
    id: str
    createdAt: datetime


class OutboxMessage(BaseModel):
    id: str
    campaignId: str
    leadId: str
    draftId: str
    channel: str
    to: str | None = None
    subject: str | None = None
    body: str
    status: OutboxStatus
    scheduledAt: datetime | None = None
    sentAt: datetime | None = None
    lastError: str | None = None
    attemptCount: int = 0
    createdAt: datetime
    updatedAt: datetime
    lead: LeadSummary | None = None


class SendAttempt(BaseModel):
    id: str
    outboxMessageId: str
    attemptNumber: int
    provider: str
    status: OutboxStatus
    responseMetadata: dict[str, Any] = Field(default_factory=dict)
    errorMessage: str | None = None
    createdAt: datetime


class DeliveryEvent(BaseModel):
    id: str
    outboxMessageId: str
    eventType: str
    payload: dict[str, Any] = Field(default_factory=dict)
    createdAt: datetime


class QueueDraftRequest(BaseModel):
    scheduledAt: datetime | None = None


class ScheduleCampaignRequest(BaseModel):
    scheduledAt: datetime | None = None


class CampaignSendResponse(BaseModel):
    campaignId: str
    queuedCount: int = 0
    sentCount: int = 0
    failedCount: int = 0
    suppressedCount: int = 0
    messages: list[OutboxMessage] = Field(default_factory=list)


class OutboxDetail(BaseModel):
    message: OutboxMessage
    attempts: list[SendAttempt] = Field(default_factory=list)
    events: list[DeliveryEvent] = Field(default_factory=list)
