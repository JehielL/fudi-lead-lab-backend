from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.security import get_current_user
from app.schemas.auth import UserResponse
from app.schemas.jobs import CrawlJob, JobRunRequest, JobRunResponse
from app.services.jobs import JobService, get_job_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[CrawlJob])
async def list_jobs(
    service: Annotated[JobService, Depends(get_job_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[CrawlJob]:
    return await service.list_jobs(limit)


@router.get("/{job_id}", response_model=CrawlJob)
async def get_job(
    job_id: str,
    service: Annotated[JobService, Depends(get_job_service)],
) -> CrawlJob:
    return await service.get_job(job_id)


@router.post("/discovery/run", response_model=JobRunResponse)
async def run_discovery(
    payload: JobRunRequest,
    service: Annotated[JobService, Depends(get_job_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> JobRunResponse:
    return await service.run_discovery(payload, current_user)


@router.post("/{job_id}/retry", response_model=JobRunResponse)
async def retry_job(
    job_id: str,
    service: Annotated[JobService, Depends(get_job_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> JobRunResponse:
    return await service.retry_job(job_id, current_user)
