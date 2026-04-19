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
        await database.leads.create_index([("enrichmentStatus", ASCENDING)])
        await database.leads.create_index([("lastEnrichedAt", DESCENDING)])
        await database.leads.create_index([("priorityScore", DESCENDING)])
        await database.leads.create_index([("updatedAt", DESCENDING)])
        await database.leads.create_index(
            [("name", TEXT), ("normalizedName", TEXT), ("city", TEXT), ("district", TEXT)]
        )
        await database.lead_sources.create_index([("leadId", ASCENDING)])
        await database.lead_sources.create_index([("sourceType", ASCENDING), ("externalId", ASCENDING)])
        await database.lead_activities.create_index([("leadId", ASCENDING), ("createdAt", DESCENDING)])
        await database.lead_status_history.create_index([("leadId", ASCENDING), ("createdAt", DESCENDING)])
        await database.crawl_jobs.create_index([("startedAt", DESCENDING)])
        await database.crawl_jobs.create_index([("status", ASCENDING), ("startedAt", DESCENDING)])
        await database.source_registry.create_index([("sourceKey", ASCENDING)], unique=True)
        await database.source_registry.create_index([("isEnabled", ASCENDING), ("priority", ASCENDING)])
        await database.raw_discovery_items.create_index([("sourceKey", ASCENDING), ("externalId", ASCENDING)])
        await database.raw_discovery_items.create_index([("processed", ASCENDING), ("createdAt", DESCENDING)])
        await database.raw_discovery_items.create_index([("createdLeadId", ASCENDING)])
        await database.page_snapshots.create_index([("leadId", ASCENDING), ("capturedAt", DESCENDING)])
        await database.page_snapshots.create_index([("url", ASCENDING)])
        await database.feature_snapshots.create_index([("leadId", ASCENDING), ("createdAt", DESCENDING)])
    except Exception:
        logger.exception("mongo_index_creation_failed")
