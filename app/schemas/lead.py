from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PipelineStatus(StrEnum):
    DETECTED = "DETECTED"
    REVIEWED = "REVIEWED"
    QUALIFIED = "QUALIFIED"
    CONTACTED = "CONTACTED"
    CONVERTED = "CONVERTED"
    PAUSED = "PAUSED"
    DISCARDED = "DISCARDED"


STATUS_STAGE_INDEX: dict[PipelineStatus, int] = {
    PipelineStatus.DETECTED: 0,
    PipelineStatus.REVIEWED: 1,
    PipelineStatus.QUALIFIED: 2,
    PipelineStatus.CONTACTED: 3,
    PipelineStatus.CONVERTED: 4,
    PipelineStatus.PAUSED: -1,
    PipelineStatus.DISCARDED: -1,
}

STATUS_LABELS: dict[PipelineStatus, str] = {
    PipelineStatus.DETECTED: "Detected",
    PipelineStatus.REVIEWED: "Reviewed",
    PipelineStatus.QUALIFIED: "Qualified",
    PipelineStatus.CONTACTED: "Contacted",
    PipelineStatus.CONVERTED: "Converted",
    PipelineStatus.PAUSED: "Paused",
    PipelineStatus.DISCARDED: "Discarded",
}

LEGACY_STATUS_MAP = {
    "new": PipelineStatus.DETECTED,
    "reviewing": PipelineStatus.REVIEWED,
    "qualified": PipelineStatus.QUALIFIED,
    "contacted": PipelineStatus.CONTACTED,
    "won": PipelineStatus.CONVERTED,
    "lost": PipelineStatus.DISCARDED,
    "discarded": PipelineStatus.DISCARDED,
}


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class ScoreBreakdown(BaseModel):
    newnessScore: int = Field(default=50, ge=0, le=100)
    digitalGapScore: int = Field(default=50, ge=0, le=100)
    fitScore: int = Field(default=50, ge=0, le=100)
    contactabilityScore: int = Field(default=50, ge=0, le=100)
    priorityScore: int = Field(default=50, ge=0, le=100)
    explanation: list[str] = Field(default_factory=list)


class LeadBase(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    normalizedName: str | None = Field(default=None, max_length=220)
    businessType: str = Field(default="restaurant", max_length=80)
    website: str | None = Field(default=None, max_length=500)
    instagram: str | None = Field(default=None, max_length=180)
    phone: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=180)
    address: str | None = Field(default=None, max_length=320)
    city: str | None = Field(default=None, max_length=120)
    district: str | None = Field(default=None, max_length=120)
    countryCode: str = Field(default="ES", min_length=2, max_length=2)
    pipelineStatus: PipelineStatus = PipelineStatus.DETECTED
    statusStageIndex: int = 0
    statusLabel: str = "Detected"
    statusUpdatedAt: datetime = Field(default_factory=lambda: datetime.now(UTC))
    priorityScore: int = Field(default=0, ge=0, le=100)
    fitScore: int = Field(default=0, ge=0, le=100)
    confidence: int = Field(default=0, ge=0, le=100)
    scoreBreakdown: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    isActive: bool = True
    isDiscarded: bool = False

    @field_validator("pipelineStatus", mode="before")
    @classmethod
    def normalize_pipeline_status(cls, value: str | PipelineStatus) -> PipelineStatus:
        if isinstance(value, PipelineStatus):
            return value
        normalized = str(value).strip()
        return LEGACY_STATUS_MAP.get(normalized.lower(), PipelineStatus(normalized.upper()))

    @field_validator("countryCode")
    @classmethod
    def uppercase_country_code(cls, value: str) -> str:
        return value.upper()


class LeadCreate(LeadBase):
    pass


class LeadUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    normalizedName: str | None = Field(default=None, max_length=220)
    businessType: str | None = Field(default=None, max_length=80)
    website: str | None = Field(default=None, max_length=500)
    instagram: str | None = Field(default=None, max_length=180)
    phone: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=180)
    address: str | None = Field(default=None, max_length=320)
    city: str | None = Field(default=None, max_length=120)
    district: str | None = Field(default=None, max_length=120)
    countryCode: str | None = Field(default=None, min_length=2, max_length=2)
    pipelineStatus: PipelineStatus | None = None
    statusStageIndex: int | None = None
    statusLabel: str | None = None
    statusUpdatedAt: datetime | None = None
    priorityScore: int | None = Field(default=None, ge=0, le=100)
    fitScore: int | None = Field(default=None, ge=0, le=100)
    confidence: int | None = Field(default=None, ge=0, le=100)
    scoreBreakdown: ScoreBreakdown | None = None
    isActive: bool | None = None
    isDiscarded: bool | None = None

    @field_validator("pipelineStatus", mode="before")
    @classmethod
    def normalize_pipeline_status(cls, value: str | PipelineStatus | None) -> PipelineStatus | None:
        if value is None or isinstance(value, PipelineStatus):
            return value
        normalized = str(value).strip()
        return LEGACY_STATUS_MAP.get(normalized.lower(), PipelineStatus(normalized.upper()))

    @field_validator("countryCode")
    @classmethod
    def uppercase_country_code(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class LeadSummary(LeadBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    schemaVersion: Literal[1] = 1
    createdAt: datetime
    updatedAt: datetime


class LeadDetail(LeadSummary):
    pass


class PaginatedLeadListResponse(BaseModel):
    items: list[LeadSummary]
    page: int
    pageSize: int
    total: int
    totalPages: int


class LeadSource(BaseModel):
    id: str
    leadId: str
    sourceType: str
    externalId: str | None = None
    sourceUrl: str | None = None
    capturedAt: datetime = Field(default_factory=lambda: datetime.now(UTC))
    rawMetadata: dict[str, Any] = Field(default_factory=dict)


class LeadActivityCreate(BaseModel):
    activityType: str = Field(min_length=1, max_length=80)
    channel: str | None = Field(default=None, max_length=80)
    description: str = Field(min_length=1, max_length=1200)


class LeadActivity(BaseModel):
    id: str
    leadId: str
    activityType: str
    channel: str | None = None
    description: str
    performedBy: str
    createdAt: datetime


class LeadStatusTransitionRequest(BaseModel):
    toStatus: PipelineStatus
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("toStatus", mode="before")
    @classmethod
    def normalize_to_status(cls, value: str | PipelineStatus) -> PipelineStatus:
        if isinstance(value, PipelineStatus):
            return value
        normalized = str(value).strip()
        return LEGACY_STATUS_MAP.get(normalized.lower(), PipelineStatus(normalized.upper()))


class LeadStatusHistory(BaseModel):
    id: str
    leadId: str
    fromStatus: PipelineStatus | None = None
    toStatus: PipelineStatus
    reason: str | None = None
    changedBy: str
    createdAt: datetime


class LeadScoreResponse(BaseModel):
    leadId: str
    scoreBreakdown: ScoreBreakdown
    priorityScore: int
    fitScore: int
    confidence: int
