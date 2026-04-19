from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.jobs import CrawlJob
from app.schemas.lead import EnrichmentStatus, LeadScoreResponse


class PageSnapshot(BaseModel):
    id: str
    leadId: str
    url: str
    snapshotType: str = "website"
    httpStatus: int | None = None
    contentType: str | None = None
    title: str | None = None
    metaDescription: str | None = None
    textExtract: str | None = None
    htmlArtifactPath: str | None = None
    capturedAt: datetime


class FeatureSnapshot(BaseModel):
    id: str
    leadId: str
    version: int = 1
    features: dict[str, Any] = Field(default_factory=dict)
    derivedSignals: dict[str, Any] = Field(default_factory=dict)
    createdAt: datetime
    sourceSnapshotIds: list[str] = Field(default_factory=list)


class LeadEnrichmentSummary(BaseModel):
    leadId: str
    status: EnrichmentStatus
    lastEnrichedAt: datetime | None = None
    lastError: str | None = None
    latestFeatureSnapshot: FeatureSnapshot | None = None
    latestPageSnapshot: PageSnapshot | None = None
    job: CrawlJob | None = None
    score: LeadScoreResponse | None = None
