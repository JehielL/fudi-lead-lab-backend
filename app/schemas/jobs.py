from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CrawlJob(BaseModel):
    id: str
    jobType: str
    status: JobStatus
    sourceType: str | None = None
    startedAt: datetime
    finishedAt: datetime | None = None
    triggeredBy: str
    processedCount: int = 0
    createdLeadCount: int = 0
    updatedLeadCount: int = 0
    errorCount: int = 0
    errorMessage: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobRunRequest(BaseModel):
    sourceKey: str | None = Field(default=None, max_length=120)
    seedItems: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobRunResponse(BaseModel):
    job: CrawlJob


class OpsSummaryResponse(BaseModel):
    jobsLast24h: int
    successfulJobsLast24h: int
    failedJobsLast24h: int
    leadsCreatedLast24h: int
    leadsUpdatedLast24h: int
    activeSources: int
    lastRun: CrawlJob | None = None
    lastError: CrawlJob | None = None
