from bson import ObjectId

from app.repositories.lead_repository import LeadRepository
from app.schemas.lead import LeadCreate, LeadUpdate


class LeadBuildResult:
    def __init__(self, lead: dict, created: bool):
        self.lead = lead
        self.created = created


class LeadBuilder:
    def __init__(self, repository: LeadRepository):
        self.repository = repository

    async def build_from_discovery_item(self, normalized_payload: dict) -> LeadBuildResult:
        existing = await self.repository.get_by_normalized_name(normalized_payload["normalizedName"])
        if existing:
            lead_id = ObjectId(existing["id"])
            updated = await self.repository.update_lead(lead_id, LeadUpdate.model_validate(normalized_payload))
            return LeadBuildResult(updated, created=False)

        created = await self.repository.create_lead(LeadCreate.model_validate(normalized_payload))
        return LeadBuildResult(created, created=True)
