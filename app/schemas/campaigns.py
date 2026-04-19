from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.lead import LeadSummary, PipelineStatus, coerce_pipeline_status


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class CampaignChannel(StrEnum):
    EMAIL = "email"
    MANUAL = "manual"
    PHONE = "phone"
    DM = "dm"


class CampaignTargetStatus(StrEnum):
    PENDING = "pending"
    DRAFTED = "drafted"
    APPROVED = "approved"
    SENT = "sent"
    RESPONDED = "responded"
    IGNORED = "ignored"
    FAILED = "failed"


class MessageDraftStatus(StrEnum):
    GENERATED = "generated"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"


class MessageTemplateType(StrEnum):
    OUTREACH = "outreach"
    FOLLOW_UP = "follow_up"


class CampaignTargetCriteria(BaseModel):
    minPriorityScore: int | None = Field(default=70, ge=0, le=100)
    pipelineStatus: PipelineStatus | None = None
    city: str | None = Field(default=None, max_length=120)
    district: str | None = Field(default=None, max_length=120)
    modelScored: bool | None = None
    enrichmentAvailable: bool | None = None
    limit: int = Field(default=50, ge=1, le=250)

    @field_validator("pipelineStatus", mode="before")
    @classmethod
    def normalize_pipeline_status(cls, value: str | PipelineStatus | None) -> PipelineStatus | None:
        return coerce_pipeline_status(value) if value is not None else None


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=1000)
    status: CampaignStatus = CampaignStatus.DRAFT
    channel: CampaignChannel = CampaignChannel.EMAIL
    targetCriteria: CampaignTargetCriteria = Field(default_factory=CampaignTargetCriteria)


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=1000)
    status: CampaignStatus | None = None
    channel: CampaignChannel | None = None
    targetCriteria: CampaignTargetCriteria | None = None


class Campaign(BaseModel):
    id: str
    name: str
    description: str | None = None
    status: CampaignStatus
    channel: CampaignChannel
    targetCriteria: CampaignTargetCriteria
    createdBy: str
    createdAt: datetime
    updatedAt: datetime


class CampaignTarget(BaseModel):
    id: str
    campaignId: str
    leadId: str
    snapshotLeadScore: int = Field(ge=0, le=100)
    snapshotPipelineStatus: PipelineStatus
    targetStatus: CampaignTargetStatus
    inclusionReason: list[str] = Field(default_factory=list)
    includedAt: datetime
    lead: LeadSummary | None = None


class CampaignTargetSelectionResponse(BaseModel):
    campaignId: str
    selectedCount: int
    skippedCount: int
    targets: list[CampaignTarget]


class MessageTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    channel: CampaignChannel = CampaignChannel.EMAIL
    templateType: MessageTemplateType = MessageTemplateType.OUTREACH
    subjectTemplate: str | None = Field(default=None, max_length=300)
    bodyTemplate: str = Field(min_length=1, max_length=4000)
    variables: list[str] = Field(default_factory=list)
    isActive: bool = True


class MessageTemplate(MessageTemplateCreate):
    id: str
    createdAt: datetime
    updatedAt: datetime


class MessageDraftUpdate(BaseModel):
    subject: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, min_length=1, max_length=5000)
    draftStatus: MessageDraftStatus | None = None


class MessageDraft(BaseModel):
    id: str
    campaignId: str
    leadId: str
    templateId: str
    channel: CampaignChannel
    subject: str | None = None
    body: str
    draftStatus: MessageDraftStatus
    generationReason: list[str] = Field(default_factory=list)
    createdAt: datetime
    updatedAt: datetime
    lead: LeadSummary | None = None
    template: MessageTemplate | None = None


class CampaignEvent(BaseModel):
    id: str
    campaignId: str
    leadId: str | None = None
    eventType: str
    payload: dict[str, Any] = Field(default_factory=dict)
    createdAt: datetime
