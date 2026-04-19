from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CollectedDiscoveryItem:
    external_id: str | None
    source_url: str | None
    raw_payload: dict[str, Any]


class DiscoveryCollector(ABC):
    @abstractmethod
    async def collect(self, source: dict[str, Any]) -> list[CollectedDiscoveryItem]:
        raise NotImplementedError
