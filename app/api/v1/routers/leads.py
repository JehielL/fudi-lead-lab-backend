from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_current_user
from app.schemas.auth import UserResponse
from app.schemas.enrichment import FeatureSnapshot, LeadEnrichmentSummary, PageSnapshot
from app.schemas.lead import (
    LeadActivity,
    LeadActivityCreate,
    LeadCreate,
    LeadDetail,
    LeadScoreResponse,
    LeadSource,
    LeadStatusHistory,
    LeadStatusTransitionRequest,
    LeadUpdate,
    PaginatedLeadListResponse,
    PipelineStatus,
    SortDirection,
)
from app.services.enrichment import EnrichmentService, get_enrichment_service
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


@router.get("/{lead_id}/status-history", response_model=list[LeadStatusHistory])
async def list_lead_status_history(
    lead_id: str,
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> list[LeadStatusHistory]:
    return await service.list_status_history(lead_id)


@router.post("/{lead_id}/status-transition", response_model=LeadDetail)
async def transition_lead_status(
    lead_id: str,
    payload: LeadStatusTransitionRequest,
    service: Annotated[LeadService, Depends(get_lead_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> LeadDetail:
    return await service.transition_status(lead_id, payload, current_user)


@router.get("/{lead_id}/score", response_model=LeadScoreResponse)
async def get_lead_score(
    lead_id: str,
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> LeadScoreResponse:
    return await service.get_score(lead_id)


@router.post("/{lead_id}/score/recompute", response_model=LeadScoreResponse)
async def recompute_lead_score(
    lead_id: str,
    service: Annotated[LeadService, Depends(get_lead_service)],
) -> LeadScoreResponse:
    return await service.recompute_score(lead_id)


@router.post("/{lead_id}/enrich", response_model=LeadEnrichmentSummary)
async def enrich_lead(
    lead_id: str,
    service: Annotated[EnrichmentService, Depends(get_enrichment_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> LeadEnrichmentSummary:
    return await service.enrich_lead(lead_id, current_user)


@router.get("/{lead_id}/enrichment", response_model=LeadEnrichmentSummary)
async def get_lead_enrichment(
    lead_id: str,
    service: Annotated[EnrichmentService, Depends(get_enrichment_service)],
) -> LeadEnrichmentSummary:
    return await service.get_summary(lead_id)


@router.get("/{lead_id}/feature-snapshots", response_model=list[FeatureSnapshot])
async def list_lead_feature_snapshots(
    lead_id: str,
    service: Annotated[EnrichmentService, Depends(get_enrichment_service)],
) -> list[FeatureSnapshot]:
    return await service.list_feature_snapshots(lead_id)


@router.get("/{lead_id}/page-snapshots", response_model=list[PageSnapshot])
async def list_lead_page_snapshots(
    lead_id: str,
    service: Annotated[EnrichmentService, Depends(get_enrichment_service)],
) -> list[PageSnapshot]:
    return await service.list_page_snapshots(lead_id)
