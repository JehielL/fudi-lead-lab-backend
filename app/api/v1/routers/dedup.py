from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.schemas.auth import UserResponse
from app.schemas.dedup import (
    DedupActionRequest,
    DedupCandidate,
    DedupCluster,
    DedupMergeRequest,
    DedupMergeResponse,
    DedupRecomputeResponse,
)
from app.services.dedup import DedupService, get_dedup_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/candidates", response_model=list[DedupCandidate])
async def list_dedup_candidates(
    service: Annotated[DedupService, Depends(get_dedup_service)],
) -> list[DedupCandidate]:
    return await service.list_candidates()


@router.get("/clusters", response_model=list[DedupCluster])
async def list_dedup_clusters(
    service: Annotated[DedupService, Depends(get_dedup_service)],
) -> list[DedupCluster]:
    return await service.list_clusters()


@router.get("/clusters/{cluster_id}", response_model=DedupCluster)
async def get_dedup_cluster(
    cluster_id: str,
    service: Annotated[DedupService, Depends(get_dedup_service)],
) -> DedupCluster:
    return await service.get_cluster(cluster_id)


@router.post("/clusters/{cluster_id}/merge", response_model=DedupMergeResponse)
async def merge_dedup_cluster(
    cluster_id: str,
    payload: DedupMergeRequest,
    service: Annotated[DedupService, Depends(get_dedup_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> DedupMergeResponse:
    return await service.merge_cluster(cluster_id, payload, current_user)


@router.post("/clusters/{cluster_id}/ignore", response_model=DedupCluster)
async def ignore_dedup_cluster(
    cluster_id: str,
    payload: DedupActionRequest,
    service: Annotated[DedupService, Depends(get_dedup_service)],
) -> DedupCluster:
    return await service.ignore_cluster(cluster_id, payload)


@router.post("/clusters/{cluster_id}/distinct", response_model=DedupCluster)
async def mark_dedup_cluster_distinct(
    cluster_id: str,
    payload: DedupActionRequest,
    service: Annotated[DedupService, Depends(get_dedup_service)],
) -> DedupCluster:
    return await service.mark_distinct(cluster_id, payload)


@router.post("/recompute", response_model=DedupRecomputeResponse)
async def recompute_dedup(
    service: Annotated[DedupService, Depends(get_dedup_service)],
) -> DedupRecomputeResponse:
    return await service.recompute()
