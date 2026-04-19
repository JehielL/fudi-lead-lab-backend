from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SourceRegistryCreate(BaseModel):
    sourceKey: str = Field(min_length=1, max_length=120)
    sourceType: str = Field(default="local_seed", min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=180)
    isEnabled: bool = True
    priority: int = Field(default=100, ge=0, le=1000)
    config: dict[str, Any] = Field(default_factory=dict)


class SourceRegistryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    isEnabled: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=1000)
    config: dict[str, Any] | None = None


class SourceRegistry(BaseModel):
    id: str
    sourceKey: str
    sourceType: str
    name: str
    isEnabled: bool
    priority: int
    config: dict[str, Any] = Field(default_factory=dict)
    createdAt: datetime
    updatedAt: datetime


class RawDiscoveryItem(BaseModel):
    id: str
    sourceType: str
    sourceKey: str
    externalId: str | None = None
    sourceUrl: str | None = None
    rawPayload: dict[str, Any]
    normalizedPayload: dict[str, Any] = Field(default_factory=dict)
    processed: bool = False
    processedAt: datetime | None = None
    createdLeadId: str | None = None
    createdAt: datetime
