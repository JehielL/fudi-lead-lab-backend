from typing import Any

from app.repositories.lead_repository import normalize_lead_name


class DiscoveryNormalizer:
    def normalize(self, raw_payload: dict[str, Any]) -> dict[str, Any]:
        name = str(raw_payload.get("name") or raw_payload.get("title") or "").strip()
        if not name:
            raise ValueError("Discovery item does not include a name")

        return {
            "name": name,
            "normalizedName": normalize_lead_name(name),
            "businessType": raw_payload.get("businessType") or raw_payload.get("category") or "restaurant",
            "website": raw_payload.get("website"),
            "instagram": raw_payload.get("instagram"),
            "phone": raw_payload.get("phone"),
            "email": raw_payload.get("email"),
            "address": raw_payload.get("address"),
            "city": raw_payload.get("city"),
            "district": raw_payload.get("district"),
            "countryCode": raw_payload.get("countryCode") or "ES",
            "pipelineStatus": raw_payload.get("pipelineStatus") or "DETECTED",
            "priorityScore": raw_payload.get("priorityScore", 50),
            "fitScore": raw_payload.get("fitScore", 50),
            "confidence": raw_payload.get("confidence", 50),
            "isActive": raw_payload.get("isActive", True),
            "isDiscarded": raw_payload.get("isDiscarded", False),
        }
