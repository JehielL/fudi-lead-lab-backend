from typing import Annotated

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.dependencies import get_database
from app.repositories.crawl_job_repository import CrawlJobRepository
from app.repositories.source_registry_repository import SourceRegistryRepository
from app.schemas.jobs import CrawlJob, JobStatus, OpsSummaryResponse


class OpsService:
    def __init__(self, database: AsyncIOMotorDatabase):
        self.jobs = CrawlJobRepository(database)
        self.sources = SourceRegistryRepository(database)

    async def get_summary(self) -> OpsSummaryResponse:
        summary = await self.jobs.summarize_last_24h()
        jobs = summary["jobs"]
        successful_jobs = [job for job in jobs if job["status"] == JobStatus.COMPLETED.value]
        failed_jobs = [job for job in jobs if job["status"] == JobStatus.FAILED.value]
        return OpsSummaryResponse(
            jobsLast24h=len(jobs),
            successfulJobsLast24h=len(successful_jobs),
            failedJobsLast24h=len(failed_jobs),
            leadsCreatedLast24h=sum(job["createdLeadCount"] for job in jobs),
            leadsUpdatedLast24h=sum(job["updatedLeadCount"] for job in jobs),
            activeSources=await self.sources.count_enabled(),
            lastRun=CrawlJob.model_validate(summary["lastRun"]) if summary["lastRun"] else None,
            lastError=CrawlJob.model_validate(summary["lastError"]) if summary["lastError"] else None,
        )


def get_ops_service(
    database: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
) -> OpsService:
    return OpsService(database)
