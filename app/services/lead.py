from typing import Annotated

from bson import ObjectId
from fastapi import Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.object_id import parse_object_id
from app.db.dependencies import get_database
from app.repositories.lead_repository import LeadRepository, calculate_total_pages
from app.schemas.auth import UserResponse
from app.schemas.lead import (
    LeadActivity,
    LeadActivityCreate,
    LeadCreate,
    LeadDetail,
    LeadSource,
    LeadSummary,
    LeadUpdate,
    PaginatedLeadListResponse,
    SortDirection,
)


class LeadService:
    def __init__(self, repository: LeadRepository):
        self.repository = repository

    async def list_leads(
        self,
        *,
        q: str | None,
        pipeline_status: str | None,
        city: str | None,
        district: str | None,
        min_priority_score: int | None,
        max_priority_score: int | None,
        page: int,
        page_size: int,
        sort_by: str,
        sort_direction: SortDirection,
    ) -> PaginatedLeadListResponse:
        items, total = await self.repository.list_leads(
            q=q,
            pipeline_status=pipeline_status,
            city=city,
            district=district,
            min_priority_score=min_priority_score,
            max_priority_score=max_priority_score,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_direction=sort_direction,
        )
        return PaginatedLeadListResponse(
            items=[LeadSummary.model_validate(item) for item in items],
            page=page,
            pageSize=page_size,
            total=total,
            totalPages=calculate_total_pages(total, page_size),
        )

    async def create_lead(self, payload: LeadCreate) -> LeadDetail:
        created = await self.repository.create_lead(payload)
        return LeadDetail.model_validate(created)

    async def get_lead(self, lead_id: str) -> LeadDetail:
        document = await self._get_existing_document(lead_id)
        return LeadDetail.model_validate(document)

    async def update_lead(self, lead_id: str, payload: LeadUpdate) -> LeadDetail:
        object_id = parse_object_id(lead_id)
        updated = await self.repository.update_lead(object_id, payload)
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        return LeadDetail.model_validate(updated)

    async def list_sources(self, lead_id: str) -> list[LeadSource]:
        object_id = parse_object_id(lead_id)
        await self._ensure_exists(object_id)
        sources = await self.repository.list_sources(object_id)
        return [LeadSource.model_validate(source) for source in sources]

    async def list_activity(self, lead_id: str) -> list[LeadActivity]:
        object_id = parse_object_id(lead_id)
        await self._ensure_exists(object_id)
        activities = await self.repository.list_activity(object_id)
        return [LeadActivity.model_validate(activity) for activity in activities]

    async def create_activity(
        self,
        lead_id: str,
        payload: LeadActivityCreate,
        current_user: UserResponse,
    ) -> LeadActivity:
        object_id = parse_object_id(lead_id)
        await self._ensure_exists(object_id)
        activity = await self.repository.create_activity(
            object_id,
            payload,
            performed_by=current_user.username,
        )
        return LeadActivity.model_validate(activity)

    async def _get_existing_document(self, lead_id: str) -> dict:
        object_id = parse_object_id(lead_id)
        document = await self.repository.get_lead(object_id)
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        return document

    async def _ensure_exists(self, lead_id: ObjectId) -> None:
        document = await self.repository.get_lead(lead_id)
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")


def get_lead_service(
    database: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
) -> LeadService:
    return LeadService(LeadRepository(database))
