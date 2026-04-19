from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING

from app.core.object_id import object_id_to_str
from app.schemas.jobs import JobStatus


def serialize_job(document: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(document)
    serialized["id"] = object_id_to_str(serialized.pop("_id", None))
    return serialized


class CrawlJobRepository:
    def __init__(self, database: AsyncIOMotorDatabase):
        self.collection = database.crawl_jobs

    async def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        cursor = self.collection.find({}).sort("startedAt", DESCENDING).limit(limit)
        return [serialize_job(document) async for document in cursor]

    async def get_job(self, job_id: ObjectId) -> dict[str, Any] | None:
        document = await self.collection.find_one({"_id": job_id})
        return serialize_job(document) if document else None

    async def create_running_job(
        self,
        *,
        job_type: str,
        source_type: str | None,
        triggered_by: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        document = {
            "jobType": job_type,
            "status": JobStatus.RUNNING.value,
            "sourceType": source_type,
            "startedAt": datetime.now(UTC),
            "finishedAt": None,
            "triggeredBy": triggered_by,
            "processedCount": 0,
            "createdLeadCount": 0,
            "updatedLeadCount": 0,
            "errorCount": 0,
            "errorMessage": None,
            "metadata": metadata,
        }
        result = await self.collection.insert_one(document)
        created = await self.collection.find_one({"_id": result.inserted_id})
        return serialize_job(created)

    async def complete_job(
        self,
        job_id: ObjectId,
        *,
        processed_count: int,
        created_lead_count: int,
        updated_lead_count: int,
        error_count: int,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        status = JobStatus.FAILED.value if error_count else JobStatus.COMPLETED.value
        await self.collection.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "status": status,
                    "finishedAt": datetime.now(UTC),
                    "processedCount": processed_count,
                    "createdLeadCount": created_lead_count,
                    "updatedLeadCount": updated_lead_count,
                    "errorCount": error_count,
                    "errorMessage": error_message,
                }
            },
        )
        updated = await self.collection.find_one({"_id": job_id})
        return serialize_job(updated)

    async def fail_job(self, job_id: ObjectId, error_message: str) -> dict[str, Any]:
        await self.collection.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "status": JobStatus.FAILED.value,
                    "finishedAt": datetime.now(UTC),
                    "errorCount": 1,
                    "errorMessage": error_message,
                }
            },
        )
        updated = await self.collection.find_one({"_id": job_id})
        return serialize_job(updated)

    async def summarize_last_24h(self) -> dict[str, Any]:
        since = datetime.now(UTC) - timedelta(hours=24)
        jobs = [serialize_job(document) async for document in self.collection.find({"startedAt": {"$gte": since}})]
        last_run_document = await self.collection.find_one(sort=[("startedAt", DESCENDING)])
        last_error_document = await self.collection.find_one(
            {"status": JobStatus.FAILED.value},
            sort=[("startedAt", DESCENDING)],
        )
        return {
            "jobs": jobs,
            "lastRun": serialize_job(last_run_document) if last_run_document else None,
            "lastError": serialize_job(last_error_document) if last_error_document else None,
        }
