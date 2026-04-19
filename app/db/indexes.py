import logging

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, TEXT

logger = logging.getLogger(__name__)


async def ensure_indexes(database: AsyncIOMotorDatabase) -> None:
    try:
        await database.leads.create_index([("normalizedName", ASCENDING)])
        await database.leads.create_index([("city", ASCENDING)])
        await database.leads.create_index([("district", ASCENDING)])
        await database.leads.create_index([("pipelineStatus", ASCENDING)])
        await database.leads.create_index([("priorityScore", DESCENDING)])
        await database.leads.create_index([("updatedAt", DESCENDING)])
        await database.leads.create_index(
            [("name", TEXT), ("normalizedName", TEXT), ("city", TEXT), ("district", TEXT)]
        )
        await database.lead_sources.create_index([("leadId", ASCENDING)])
        await database.lead_sources.create_index([("sourceType", ASCENDING), ("externalId", ASCENDING)])
        await database.lead_activities.create_index([("leadId", ASCENDING), ("createdAt", DESCENDING)])
    except Exception:
        logger.exception("mongo_index_creation_failed")
