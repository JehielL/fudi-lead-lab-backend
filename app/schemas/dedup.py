from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.lead import LeadSummary


class DedupStatus(StrEnum):
    OPEN = "open"
    MERGED = "merged"
    IGNORED = "ignored"
    DISTINCT = "distinct"


class DedupCandidate(BaseModel):
    id: str
    leadIds: list[str]
    clusterId: str | None = None
    score: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)
    matchedFields: list[str] = Field(default_factory=list)
    status: DedupStatus = DedupStatus.OPEN
    createdAt: datetime
    updatedAt: datetime
    leads: list[LeadSummary] = Field(default_factory=list)


class DedupCluster(BaseModel):
    id: str
    leadIds: list[str]
    candidateIds: list[str] = Field(default_factory=list)
    score: float = Field(ge=0, le=1)
    status: DedupStatus = DedupStatus.OPEN
    createdAt: datetime
    updatedAt: datetime
    mergedIntoLeadId: str | None = None
    leads: list[LeadSummary] = Field(default_factory=list)


class DedupRecomputeResponse(BaseModel):
    candidateCount: int
    clusterCount: int


class DedupMergeRequest(BaseModel):
    primaryLeadId: str | None = None
    reason: str | None = Field(default=None, max_length=500)


class DedupActionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class MergeEvent(BaseModel):
    id: str
    clusterId: str
    primaryLeadId: str
    mergedLeadIds: list[str]
    mergedFields: dict[str, Any] = Field(default_factory=dict)
    performedBy: str
    reason: str | None = None
    createdAt: datetime


class DedupMergeResponse(BaseModel):
    cluster: DedupCluster
    event: MergeEvent
