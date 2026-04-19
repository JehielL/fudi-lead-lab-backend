from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.crawl_job_repository import CrawlJobRepository
from app.repositories.lead_repository import LeadRepository
from app.repositories.raw_discovery_item_repository import RawDiscoveryItemRepository
from app.repositories.source_registry_repository import SourceRegistryRepository
from app.schemas.jobs import JobRunRequest
from app.workers.discovery.collectors.local_seed import LocalSeedCollector
from app.workers.discovery.processing.lead_builder import LeadBuilder
from app.workers.discovery.processing.normalizer import DiscoveryNormalizer


class DiscoveryOrchestrator:
    def __init__(self, database: AsyncIOMotorDatabase):
        self.database = database
        self.jobs = CrawlJobRepository(database)
        self.sources = SourceRegistryRepository(database)
        self.raw_items = RawDiscoveryItemRepository(database)
        self.leads = LeadRepository(database)
        self.normalizer = DiscoveryNormalizer()

    async def run(self, request: JobRunRequest, triggered_by: str) -> dict:
        sources = await self._resolve_sources(request)
        source_type = sources[0]["sourceType"] if len(sources) == 1 else "mixed"
        job = await self.jobs.create_running_job(
            job_type="discovery",
            source_type=source_type,
            triggered_by=triggered_by,
            metadata={**request.metadata, "sourceCount": len(sources), "sourceKey": request.sourceKey},
        )
        job_id = ObjectId(job["id"])
        processed_count = 0
        created_count = 0
        updated_count = 0
        error_count = 0
        error_messages: list[str] = []
        builder = LeadBuilder(self.leads)

        try:
            for source in sources:
                collector = self._collector_for(source)
                collected_items = await collector.collect(source)
                for item in collected_items:
                    raw_item = await self.raw_items.create_item(
                        source_type=source["sourceType"],
                        source_key=source["sourceKey"],
                        external_id=item.external_id,
                        source_url=item.source_url,
                        raw_payload=item.raw_payload,
                    )
                    try:
                        normalized = self.normalizer.normalize(item.raw_payload)
                        result = await builder.build_from_discovery_item(normalized)
                        lead_object_id = ObjectId(result.lead["id"])
                        await self.leads.create_source(
                            lead_id=lead_object_id,
                            source_type=source["sourceType"],
                            external_id=item.external_id,
                            source_url=item.source_url,
                            raw_metadata={"rawDiscoveryItemId": raw_item["id"], "sourceKey": source["sourceKey"]},
                        )
                        await self.raw_items.mark_processed(
                            ObjectId(raw_item["id"]),
                            normalized_payload=normalized,
                            created_lead_id=lead_object_id,
                        )
                        processed_count += 1
                        if result.created:
                            created_count += 1
                        else:
                            updated_count += 1
                    except Exception as exc:
                        error_count += 1
                        error_messages.append(str(exc))

            return await self.jobs.complete_job(
                job_id,
                processed_count=processed_count,
                created_lead_count=created_count,
                updated_lead_count=updated_count,
                error_count=error_count,
                error_message="; ".join(error_messages[:3]) if error_messages else None,
            )
        except Exception as exc:
            return await self.jobs.fail_job(job_id, str(exc))

    async def retry(self, previous_job: dict, triggered_by: str) -> dict:
        metadata = dict(previous_job.get("metadata") or {})
        source_key = metadata.get("sourceKey")
        return await self.run(JobRunRequest(sourceKey=source_key, metadata={"retryOf": previous_job["id"]}), triggered_by)

    async def _resolve_sources(self, request: JobRunRequest) -> list[dict]:
        if request.seedItems:
            return [
                {
                    "sourceKey": request.sourceKey or "manual-seed",
                    "sourceType": "local_seed",
                    "name": "Manual seed",
                    "isEnabled": True,
                    "priority": 0,
                    "config": {"seedItems": request.seedItems},
                }
            ]
        if request.sourceKey:
            source = await self.sources.get_by_key(request.sourceKey)
            if not source or not source["isEnabled"]:
                raise ValueError("Source is not enabled or does not exist")
            return [source]
        sources = await self.sources.list_sources(enabled_only=True)
        if not sources:
            raise ValueError("No enabled sources available")
        return sources

    def _collector_for(self, source: dict) -> LocalSeedCollector:
        if source["sourceType"] != "local_seed":
            raise ValueError(f"Unsupported sourceType: {source['sourceType']}")
        return LocalSeedCollector()
