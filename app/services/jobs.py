from typing import Annotated

from fastapi import Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.object_id import parse_object_id
from app.db.dependencies import get_database
from app.repositories.crawl_job_repository import CrawlJobRepository
from app.schemas.auth import UserResponse
from app.schemas.jobs import CrawlJob, JobRunRequest, JobRunResponse
from app.workers.jobs.runner import JobRunner


class JobService:
    def __init__(self, database: AsyncIOMotorDatabase):
        self.database = database
        self.repository = CrawlJobRepository(database)

    async def list_jobs(self, limit: int) -> list[CrawlJob]:
        jobs = await self.repository.list_jobs(limit)
        return [CrawlJob.model_validate(job) for job in jobs]

    async def get_job(self, job_id: str) -> CrawlJob:
        document = await self.repository.get_job(parse_object_id(job_id))
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        return CrawlJob.model_validate(document)

    async def run_discovery(self, request: JobRunRequest, current_user: UserResponse) -> JobRunResponse:
        runner = JobRunner(self.database)
        job = await runner.run_discovery(request, triggered_by=current_user.username)
        return JobRunResponse(job=CrawlJob.model_validate(job))

    async def retry_job(self, job_id: str, current_user: UserResponse) -> JobRunResponse:
        previous_job = await self.repository.get_job(parse_object_id(job_id))
        if previous_job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        if previous_job["jobType"] != "discovery":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only discovery jobs can be retried")
        runner = JobRunner(self.database)
        job = await runner.retry_discovery(previous_job, triggered_by=current_user.username)
        return JobRunResponse(job=CrawlJob.model_validate(job))


def get_job_service(
    database: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
) -> JobService:
    return JobService(database)
