import re
import unicodedata
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Annotated, Any
from urllib.parse import urlparse

from bson import ObjectId
from fastapi import Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.object_id import parse_object_id
from app.db.dependencies import get_database
from app.repositories.dedup_repository import DedupRepository
from app.repositories.lead_repository import serialize_document
from app.schemas.auth import UserResponse
from app.schemas.dedup import (
    DedupActionRequest,
    DedupCandidate,
    DedupCluster,
    DedupMergeRequest,
    DedupMergeResponse,
    DedupRecomputeResponse,
    DedupStatus,
    MergeEvent,
)
from app.schemas.lead import LeadSummary


class DedupService:
    def __init__(self, repository: DedupRepository):
        self.repository = repository

    async def list_candidates(self) -> list[DedupCandidate]:
        documents = await self.repository.list_candidate_documents()
        return [await self._candidate_with_leads(document) for document in documents]

    async def list_clusters(self) -> list[DedupCluster]:
        documents = await self.repository.list_cluster_documents()
        return [await self._cluster_with_leads(document) for document in documents]

    async def get_cluster(self, cluster_id: str) -> DedupCluster:
        document = await self._get_cluster_document(cluster_id)
        return await self._cluster_with_leads(document)

    async def recompute(self) -> DedupRecomputeResponse:
        now = datetime.now(UTC)
        leads = await self.repository.list_active_leads()
        suppressed_pairs = await self.repository.get_suppressed_pairs()
        candidates = self._build_candidates(leads, suppressed_pairs, now)
        clusters = self._build_clusters(candidates, now)
        candidate_count, cluster_count = await self.repository.replace_open_candidates_and_clusters(candidates, clusters)
        return DedupRecomputeResponse(candidateCount=candidate_count, clusterCount=cluster_count)

    async def merge_cluster(
        self,
        cluster_id: str,
        payload: DedupMergeRequest,
        current_user: UserResponse,
    ) -> DedupMergeResponse:
        cluster_document = await self._get_cluster_document(cluster_id)
        if cluster_document["status"] != DedupStatus.OPEN.value:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cluster is not open")
        lead_ids = [parse_object_id(value) for value in cluster_document["leadIds"]]
        primary_lead_id = parse_object_id(payload.primaryLeadId) if payload.primaryLeadId else lead_ids[0]
        if primary_lead_id not in lead_ids:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Primary lead is not in cluster")
        merged_lead_ids = [lead_id for lead_id in lead_ids if lead_id != primary_lead_id]
        if not merged_lead_ids:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cluster has no duplicate leads")
        event = await self.repository.merge_cluster(
            cluster_id=parse_object_id(cluster_id),
            primary_lead_id=primary_lead_id,
            merged_lead_ids=merged_lead_ids,
            performed_by=current_user.username,
            reason=payload.reason,
        )
        updated_cluster = await self._get_cluster_document(cluster_id)
        return DedupMergeResponse(
            cluster=await self._cluster_with_leads(updated_cluster),
            event=MergeEvent.model_validate(event),
        )

    async def ignore_cluster(self, cluster_id: str, payload: DedupActionRequest) -> DedupCluster:
        _ = payload
        document = await self.repository.mark_cluster(parse_object_id(cluster_id), DedupStatus.IGNORED.value)
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dedup cluster not found")
        return await self._cluster_with_leads(document)

    async def mark_distinct(self, cluster_id: str, payload: DedupActionRequest) -> DedupCluster:
        _ = payload
        document = await self.repository.mark_cluster(parse_object_id(cluster_id), DedupStatus.DISTINCT.value)
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dedup cluster not found")
        return await self._cluster_with_leads(document)

    async def _get_cluster_document(self, cluster_id: str) -> dict[str, Any]:
        document = await self.repository.get_cluster_document(parse_object_id(cluster_id))
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dedup cluster not found")
        return document

    async def _candidate_with_leads(self, document: dict[str, Any]) -> DedupCandidate:
        document["leads"] = await self._lead_summaries(document["leadIds"])
        return DedupCandidate.model_validate(document)

    async def _cluster_with_leads(self, document: dict[str, Any]) -> DedupCluster:
        document["leads"] = await self._lead_summaries(document["leadIds"])
        return DedupCluster.model_validate(document)

    async def _lead_summaries(self, lead_ids: list[str]) -> list[LeadSummary]:
        object_ids = [ObjectId(value) for value in lead_ids if ObjectId.is_valid(value)]
        documents = await self.repository.get_leads_by_ids(object_ids)
        return [LeadSummary.model_validate(serialize_document(document)) for document in documents]

    def _build_candidates(
        self,
        leads: list[dict[str, Any]],
        suppressed_pairs: set[tuple[str, str]],
        now: datetime,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for index, left in enumerate(leads):
            for right in leads[index + 1 :]:
                pair = tuple(sorted([str(left["_id"]), str(right["_id"])]))
                if pair in suppressed_pairs:
                    continue
                score, reasons, matched_fields = self._similarity(left, right)
                if score < 0.72:
                    continue
                candidates.append(
                    {
                        "_id": ObjectId(),
                        "leadIds": [left["_id"], right["_id"]],
                        "clusterId": None,
                        "score": score,
                        "reasons": reasons,
                        "matchedFields": matched_fields,
                        "status": DedupStatus.OPEN.value,
                        "createdAt": now,
                        "updatedAt": now,
                    }
                )
        return candidates

    def _build_clusters(self, candidates: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
        parent: dict[str, str] = {}

        def find(value: str) -> str:
            parent.setdefault(value, value)
            if parent[value] != value:
                parent[value] = find(parent[value])
            return parent[value]

        def union(left: str, right: str) -> None:
            parent[find(right)] = find(left)

        for candidate in candidates:
            lead_ids = [str(value) for value in candidate["leadIds"]]
            union(lead_ids[0], lead_ids[1])

        groups: dict[str, list[dict[str, Any]]] = {}
        for candidate in candidates:
            root = find(str(candidate["leadIds"][0]))
            groups.setdefault(root, []).append(candidate)

        clusters: list[dict[str, Any]] = []
        for group_candidates in groups.values():
            cluster_id = ObjectId()
            lead_id_set = {
                lead_id
                for candidate in group_candidates
                for lead_id in candidate["leadIds"]
            }
            scores = [candidate["score"] for candidate in group_candidates]
            for candidate in group_candidates:
                candidate["clusterId"] = cluster_id
            clusters.append(
                {
                    "_id": cluster_id,
                    "leadIds": list(lead_id_set),
                    "candidateIds": [candidate["_id"] for candidate in group_candidates],
                    "score": round(sum(scores) / len(scores), 3),
                    "status": DedupStatus.OPEN.value,
                    "createdAt": now,
                    "updatedAt": now,
                    "mergedIntoLeadId": None,
                }
            )
        return clusters

    def _similarity(self, left: dict[str, Any], right: dict[str, Any]) -> tuple[float, list[str], list[str]]:
        reasons: list[str] = []
        matched_fields: list[str] = []
        score = 0.0

        exact_checks = [
            ("email", self._normalize_email(left.get("email")), self._normalize_email(right.get("email")), 0.98),
            ("phone", self._normalize_phone(left.get("phone")), self._normalize_phone(right.get("phone")), 0.95),
            ("website", self._normalize_website(left.get("website")), self._normalize_website(right.get("website")), 0.92),
        ]
        for field, left_value, right_value, field_score in exact_checks:
            if left_value and right_value and left_value == right_value:
                score = max(score, field_score)
                matched_fields.append(field)
                reasons.append(f"Exact {field} match.")

        left_name = self._normalize_text(left.get("normalizedName") or left.get("name"))
        right_name = self._normalize_text(right.get("normalizedName") or right.get("name"))
        name_similarity = SequenceMatcher(None, left_name, right_name).ratio() if left_name and right_name else 0
        location_boost = 0.0
        if self._normalize_text(left.get("city")) and self._normalize_text(left.get("city")) == self._normalize_text(right.get("city")):
            location_boost += 0.08
            matched_fields.append("city")
        if self._normalize_text(left.get("district")) and self._normalize_text(left.get("district")) == self._normalize_text(right.get("district")):
            location_boost += 0.05
            matched_fields.append("district")
        address_similarity = SequenceMatcher(
            None,
            self._normalize_text(left.get("address")),
            self._normalize_text(right.get("address")),
        ).ratio()
        if address_similarity >= 0.82:
            location_boost += 0.08
            matched_fields.append("address")
            reasons.append("Similar address.")
        if name_similarity >= 0.82:
            score = max(score, min(0.98, name_similarity * 0.82 + location_boost))
            matched_fields.append("normalizedName")
            reasons.append("Similar normalized name.")

        return round(min(score, 1), 3), list(dict.fromkeys(reasons)), list(dict.fromkeys(matched_fields))

    def _normalize_text(self, value: Any) -> str:
        if not value:
            return ""
        normalized = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()

    def _normalize_email(self, value: Any) -> str:
        return str(value).strip().lower() if value else ""

    def _normalize_phone(self, value: Any) -> str:
        return re.sub(r"\D+", "", str(value)) if value else ""

    def _normalize_website(self, value: Any) -> str:
        if not value:
            return ""
        url = str(value).strip().lower()
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        parsed = urlparse(url)
        host = parsed.netloc.removeprefix("www.")
        path = parsed.path.rstrip("/")
        return f"{host}{path}"


def get_dedup_service(
    database: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
) -> DedupService:
    return DedupService(DedupRepository(database))
