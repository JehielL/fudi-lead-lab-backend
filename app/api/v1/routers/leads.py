from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_current_user
from app.schemas.auth import UserResponse
from app.schemas.lead import (
    LeadActivity,
    LeadActivityCreate,
    LeadCreate,
    LeadDetail,
    LeadSource,
    LeadUpdate,
    PaginatedLeadListResponse,
    PipelineStatus,
    SortDirection,
)
from app.services.lead import LeadService, get_lead_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=PaginatedLeadListResponse)
async def list_leads(
    service: Annotated[LeadService, Depends(get_lead_service)],
    q: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    pipelineStatus: PipelineStatus | None = None,
    city: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    district: Annotated[str | None, Query(min_length=1, max_length=120)] = None,
    minPriorityScore: Annotated[int | None, Query(ge=0, le=100)] = None,
    maxPriorityScore: Annotated[int | None, Query(ge=0, le=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    pageSize: Annotated[int, Query(ge=1, le=100)] = 25,
    sortBy: str = "updatedAt",
    sortDirection: SortDirection = SortDirection.DESC,
) -> PaginatedLeadListResponse:
    if (
        minPriorityScore is not None
        and maxPriorityScore is not None
        and minPriorityScore > maxPriorityScore
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="minPriorityScore cannot be greater than maxPriorityScore",
        )

    return await service.list_leads(
        q=q,
        pipeline_status=pipelineStatus.value if pipelineStatus else None,
        city=city,
        district=district,
        min_priority_score=minPriorityScore,
        max_priority_score=maxPriorityScore,
        page=page,
        page_size=pageSize,
        sort_by=sortBy,
        sort_direction=sortDirection,
    )


@router.post("", response_model=LeadDetail, status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: LeadCreate,
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> LeadDetail:
    return await service.create_lead(payload)


@router.get("/{lead_id}", response_model=LeadDetail)
async def get_lead(
    lead_id: str,
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> LeadDetail:
    return await service.get_lead(lead_id)


@router.patch("/{lead_id}", response_model=LeadDetail)
async def update_lead(
    lead_id: str,
    payload: LeadUpdate,
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> LeadDetail:
    return await service.update_lead(lead_id, payload)


@router.get("/{lead_id}/sources", response_model=list[LeadSource])
async def list_lead_sources(
    lead_id: str,
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> list[LeadSource]:
    return await service.list_sources(lead_id)


@router.get("/{lead_id}/activity", response_model=list[LeadActivity])
async def list_lead_activity(
    lead_id: str,
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> list[LeadActivity]:
    return await service.list_activity(lead_id)


@router.post("/{lead_id}/activity", response_model=LeadActivity, status_code=status.HTTP_201_CREATED)
async def create_lead_activity(
    lead_id: str,
    payload: LeadActivityCreate,
    service: Annotated[LeadService, Depends(get_lead_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> LeadActivity:
    return await service.create_activity(lead_id, payload, current_user)
