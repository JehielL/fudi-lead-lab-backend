from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

HealthStatus = Literal["ok", "degraded", "error"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str = "fudi-lead-lab-backend"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DependencyStatus(BaseModel):
    status: HealthStatus
    detail: str | None = None


class HealthDependenciesResponse(BaseModel):
    status: HealthStatus
    dependencies: dict[str, DependencyStatus]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

