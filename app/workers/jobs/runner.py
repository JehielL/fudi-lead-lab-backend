from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.jobs import JobRunRequest
from app.workers.discovery.orchestrator import DiscoveryOrchestrator


class JobRunner:
    def __init__(self, database: AsyncIOMotorDatabase):
        self.discovery = DiscoveryOrchestrator(database)

    async def run_discovery(self, request: JobRunRequest, triggered_by: str) -> dict:
        return await self.discovery.run(request, triggered_by)

    async def retry_discovery(self, previous_job: dict, triggered_by: str) -> dict:
        return await self.discovery.retry(previous_job, triggered_by)
