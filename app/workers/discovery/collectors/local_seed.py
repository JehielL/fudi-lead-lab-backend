from typing import Any

from app.workers.discovery.collectors.base import CollectedDiscoveryItem, DiscoveryCollector

DEFAULT_SEED_ITEMS: list[dict[str, Any]] = [
    {
        "name": "Fudi Seed Bistro",
        "businessType": "restaurant",
        "website": "https://example.com/fudi-seed-bistro",
        "instagram": "@fudiseedbistro",
        "city": "Madrid",
        "district": "Centro",
        "countryCode": "ES",
        "priorityScore": 62,
        "fitScore": 58,
        "confidence": 55,
    }
]


class LocalSeedCollector(DiscoveryCollector):
    async def collect(self, source: dict[str, Any]) -> list[CollectedDiscoveryItem]:
        config = source.get("config") or {}
        seed_items = config.get("seedItems") or DEFAULT_SEED_ITEMS
        collected: list[CollectedDiscoveryItem] = []
        for index, item in enumerate(seed_items, start=1):
            external_id = item.get("externalId") or f"{source['sourceKey']}:{index}:{item.get('name', 'item')}"
            collected.append(
                CollectedDiscoveryItem(
                    external_id=external_id,
                    source_url=item.get("sourceUrl") or item.get("website"),
                    raw_payload=dict(item),
                )
            )
        return collected
