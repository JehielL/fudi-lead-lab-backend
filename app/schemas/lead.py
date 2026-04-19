from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PipelineStatus(StrEnum):
    NEW = "new"
    REVIEWING = "reviewing"
    QUALIFIED = "qualified"
    CONTACTED = "contacted"
    WON = "won"
    LOST = "lost"
    DISCARDED = "discarded"


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


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
    pipelineStatus: PipelineStatus = PipelineStatus.NEW
    priorityScore: int = Field(default=0, ge=0, le=100)
    fitScore: int = Field(default=0, ge=0, le=100)
    confidence: int = Field(default=0, ge=0, le=100)
    isActive: bool = True
    isDiscarded: bool = False

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
    priorityScore: int | None = Field(default=None, ge=0, le=100)
    fitScore: int | None = Field(default=None, ge=0, le=100)
    confidence: int | None = Field(default=None, ge=0, le=100)
    isActive: bool | None = None
    isDiscarded: bool | None = None

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
