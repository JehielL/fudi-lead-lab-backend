from typing import Annotated

from bson import ObjectId
from fastapi import Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.object_id import parse_object_id
from app.db.dependencies import get_database
from app.repositories.lead_repository import LeadRepository, calculate_total_pages
from app.schemas.auth import UserResponse
from app.schemas.lead import (
    LeadActivity,
    LeadActivityCreate,
    LeadCreate,
    LeadDetail,
    LeadScoreResponse,
    LeadSource,
    LeadStatusHistory,
    LeadStatusTransitionRequest,
    LeadSummary,
    LeadUpdate,
    PaginatedLeadListResponse,
    PipelineStatus,
    ScoreBreakdown,
    SortDirection,
)

MAIN_FLOW = [
    PipelineStatus.DETECTED,
    PipelineStatus.REVIEWED,
    PipelineStatus.QUALIFIED,
    PipelineStatus.CONTACTED,
    PipelineStatus.CONVERTED,
]


class LeadService:
    def __init__(self, repository: LeadRepository):
        self.repository = repository

    async def list_leads(
        self,
        *,
        q: str | None,
        pipeline_status: str | None,
        city: str | None,
        district: str | None,
        min_priority_score: int | None,
        max_priority_score: int | None,
        page: int,
        page_size: int,
        sort_by: str,
        sort_direction: SortDirection,
    ) -> PaginatedLeadListResponse:
        items, total = await self.repository.list_leads(
            q=q,
            pipeline_status=pipeline_status,
            city=city,
            district=district,
            min_priority_score=min_priority_score,
            max_priority_score=max_priority_score,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_direction=sort_direction,
        )
        return PaginatedLeadListResponse(
            items=[LeadSummary.model_validate(item) for item in items],
            page=page,
            pageSize=page_size,
            total=total,
            totalPages=calculate_total_pages(total, page_size),
        )

    async def create_lead(self, payload: LeadCreate) -> LeadDetail:
        created = await self.repository.create_lead(payload)
        return LeadDetail.model_validate(created)

    async def get_lead(self, lead_id: str) -> LeadDetail:
        document = await self._get_existing_document(lead_id)
        return LeadDetail.model_validate(document)

    async def update_lead(self, lead_id: str, payload: LeadUpdate) -> LeadDetail:
        object_id = parse_object_id(lead_id)
        updated = await self.repository.update_lead(object_id, payload)
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        return LeadDetail.model_validate(updated)

    async def list_sources(self, lead_id: str) -> list[LeadSource]:
        object_id = parse_object_id(lead_id)
        await self._ensure_exists(object_id)
        sources = await self.repository.list_sources(object_id)
        return [LeadSource.model_validate(source) for source in sources]

    async def list_activity(self, lead_id: str) -> list[LeadActivity]:
        object_id = parse_object_id(lead_id)
        await self._ensure_exists(object_id)
        activities = await self.repository.list_activity(object_id)
        return [LeadActivity.model_validate(activity) for activity in activities]

    async def create_activity(
        self,
        lead_id: str,
        payload: LeadActivityCreate,
        current_user: UserResponse,
    ) -> LeadActivity:
        object_id = parse_object_id(lead_id)
        await self._ensure_exists(object_id)
        activity = await self.repository.create_activity(
            object_id,
            payload,
            performed_by=current_user.username,
        )
        return LeadActivity.model_validate(activity)

    async def list_status_history(self, lead_id: str) -> list[LeadStatusHistory]:
        object_id = parse_object_id(lead_id)
        await self._ensure_exists(object_id)
        history = await self.repository.list_status_history(object_id)
        return [LeadStatusHistory.model_validate(item) for item in history]

    async def transition_status(
        self,
        lead_id: str,
        payload: LeadStatusTransitionRequest,
        current_user: UserResponse,
    ) -> LeadDetail:
        object_id = parse_object_id(lead_id)
        current = await self._get_existing_document(lead_id)
        current_detail = LeadDetail.model_validate(current)
        from_status = current_detail.pipelineStatus
        to_status = payload.toStatus
        if not self._is_valid_transition(from_status, to_status):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status transition from {from_status.value} to {to_status.value}",
            )
        updated = await self.repository.transition_status(
            object_id,
            from_status=from_status,
            to_status=to_status,
            reason=payload.reason,
            changed_by=current_user.username,
        )
        return LeadDetail.model_validate(updated)

    async def get_score(self, lead_id: str) -> LeadScoreResponse:
        document = await self._get_existing_document(lead_id)
        lead = LeadDetail.model_validate(document)
        return LeadScoreResponse(
            leadId=lead.id,
            scoreBreakdown=lead.scoreBreakdown,
            priorityScore=lead.priorityScore,
            fitScore=lead.fitScore,
            confidence=lead.confidence,
        )

    async def recompute_score(self, lead_id: str) -> LeadScoreResponse:
        object_id = parse_object_id(lead_id)
        document = await self._get_existing_document(lead_id)
        lead = LeadDetail.model_validate(document)
        score_breakdown, confidence = self._compute_score(lead)
        updated = await self.repository.update_score(
            object_id,
            score_breakdown=score_breakdown,
            confidence=confidence,
        )
        updated_lead = LeadDetail.model_validate(updated)
        return LeadScoreResponse(
            leadId=updated_lead.id,
            scoreBreakdown=updated_lead.scoreBreakdown,
            priorityScore=updated_lead.priorityScore,
            fitScore=updated_lead.fitScore,
            confidence=updated_lead.confidence,
        )

    async def _get_existing_document(self, lead_id: str) -> dict:
        object_id = parse_object_id(lead_id)
        document = await self.repository.get_lead(object_id)
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        return document

    async def _ensure_exists(self, lead_id: ObjectId) -> None:
        document = await self.repository.get_lead(lead_id)
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    def _is_valid_transition(self, from_status: PipelineStatus, to_status: PipelineStatus) -> bool:
        if from_status == to_status:
            return True
        if to_status in {PipelineStatus.PAUSED, PipelineStatus.DISCARDED}:
            return from_status != PipelineStatus.CONVERTED
        if from_status == PipelineStatus.PAUSED:
            return to_status in MAIN_FLOW
        if from_status in {PipelineStatus.DISCARDED, PipelineStatus.CONVERTED}:
            return False
        if from_status not in MAIN_FLOW or to_status not in MAIN_FLOW:
            return False
        return MAIN_FLOW.index(to_status) == MAIN_FLOW.index(from_status) + 1

    def _compute_score(self, lead: LeadDetail) -> tuple[ScoreBreakdown, int]:
        explanation: list[str] = []
        newness_score = 75 if lead.pipelineStatus == PipelineStatus.DETECTED else 55
        if lead.pipelineStatus == PipelineStatus.DETECTED:
            explanation.append("Lead is newly detected and needs review.")

        digital_gap_score = 35
        if not lead.website:
            digital_gap_score += 25
            explanation.append("No website detected.")
        if not lead.instagram:
            digital_gap_score += 12
            explanation.append("No Instagram profile captured.")
        if lead.website and lead.instagram:
            explanation.append("Website and Instagram are already present.")
        digital_gap_score = min(digital_gap_score, 100)

        fit_score = lead.fitScore or 50
        if (lead.businessType or "").lower() in {"restaurant", "bar", "bistro", "cafe"}:
            fit_score = max(fit_score, 70)
            explanation.append("Business type matches FUDI restaurant focus.")

        contactability_score = 25
        if lead.phone:
            contactability_score += 25
            explanation.append("Phone is available.")
        if lead.email:
            contactability_score += 25
            explanation.append("Email is available.")
        if lead.website or lead.instagram:
            contactability_score += 15
        contactability_score = min(contactability_score, 100)

        priority_score = round(
            newness_score * 0.2
            + digital_gap_score * 0.3
            + fit_score * 0.3
            + contactability_score * 0.2
        )
        confidence = round((contactability_score + fit_score) / 2)
        if not explanation:
            explanation.append("Baseline score computed from available lead attributes.")

        return (
            ScoreBreakdown(
                newnessScore=newness_score,
                digitalGapScore=digital_gap_score,
                fitScore=fit_score,
                contactabilityScore=contactability_score,
                priorityScore=priority_score,
                explanation=explanation,
            ),
            confidence,
        )


def get_lead_service(
    database: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
) -> LeadService:
    return LeadService(LeadRepository(database))
