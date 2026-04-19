import re
from typing import Annotated, Any

from bson import ObjectId
from fastapi import Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.object_id import parse_object_id
from app.db.dependencies import get_database
from app.repositories.campaign_repository import CampaignRepository
from app.schemas.auth import UserResponse
from app.schemas.campaigns import (
    Campaign,
    CampaignChannel,
    CampaignCreate,
    CampaignEvent,
    CampaignStatus,
    CampaignTarget,
    CampaignTargetCriteria,
    CampaignTargetSelectionResponse,
    CampaignTargetStatus,
    CampaignUpdate,
    MessageDraft,
    MessageDraftStatus,
    MessageDraftUpdate,
    MessageTemplate,
    MessageTemplateCreate,
    MessageTemplateType,
)
from app.schemas.lead import LeadSummary, PipelineStatus


COMMERCIAL_STATUSES = {
    PipelineStatus.QUALIFIED,
    PipelineStatus.CONTACTED,
    PipelineStatus.CONVERTED,
}


DEFAULT_TEMPLATE = MessageTemplateCreate(
    name="FUDI qualified lead intro",
    channel=CampaignChannel.EMAIL,
    templateType=MessageTemplateType.OUTREACH,
    subjectTemplate="FUDI opportunity for {{leadName}}",
    bodyTemplate=(
        "Hi {{leadName}},\n\n"
        "We noticed {{reasonSummary}} in {{district}}, {{city}}. "
        "Your current lead score is {{priorityScore}} and the pipeline status is {{pipelineStatus}}.\n\n"
        "FUDI can help turn that demand signal into cleaner bookings and better guest operations.\n\n"
        "Best,\nFUDI"
    ),
    variables=[
        "leadName",
        "district",
        "city",
        "priorityScore",
        "pipelineStatus",
        "website",
        "bookingHint",
        "reasonSummary",
    ],
)


class CampaignService:
    def __init__(self, repository: CampaignRepository):
        self.repository = repository

    async def list_campaigns(self) -> list[Campaign]:
        campaigns = await self.repository.list_campaigns()
        return [Campaign.model_validate(campaign) for campaign in campaigns]

    async def create_campaign(self, payload: CampaignCreate, current_user: UserResponse) -> Campaign:
        document = payload.model_dump()
        document["createdBy"] = current_user.username
        campaign = await self.repository.create_campaign(document)
        campaign_id = parse_object_id(campaign["id"])
        await self.repository.create_event(
            campaign_id=campaign_id,
            event_type="campaign_created",
            payload={"createdBy": current_user.username, "status": campaign["status"]},
        )
        return Campaign.model_validate(campaign)

    async def get_campaign(self, campaign_id: str) -> Campaign:
        campaign = await self._get_campaign_document(campaign_id)
        return Campaign.model_validate(campaign)

    async def update_campaign(
        self,
        campaign_id: str,
        payload: CampaignUpdate,
        current_user: UserResponse,
    ) -> Campaign:
        object_id = parse_object_id(campaign_id)
        await self._ensure_campaign(object_id)
        update_data = payload.model_dump(exclude_unset=True)
        updated = await self.repository.update_campaign(object_id, update_data)
        await self.repository.create_event(
            campaign_id=object_id,
            event_type="campaign_updated",
            payload={"updatedBy": current_user.username, "changedFields": sorted(update_data.keys())},
        )
        return Campaign.model_validate(updated)

    async def select_targets(
        self,
        campaign_id: str,
        current_user: UserResponse,
    ) -> CampaignTargetSelectionResponse:
        campaign = Campaign.model_validate(await self._get_campaign_document(campaign_id))
        object_id = parse_object_id(campaign_id)
        criteria = campaign.targetCriteria or CampaignTargetCriteria()
        candidate_leads = await self.repository.list_selectable_leads(criteria)
        targets: list[CampaignTarget] = []
        skipped_count = 0
        for lead in candidate_leads:
            lead_summary = LeadSummary.model_validate(lead)
            if not self._is_commercially_eligible(lead_summary, criteria):
                skipped_count += 1
                continue
            lead_id = parse_object_id(lead_summary.id)
            reasons = self._target_reasons(lead_summary, criteria)
            target = await self.repository.upsert_target(
                campaign_id=object_id,
                lead_id=lead_id,
                document={
                    "snapshotLeadScore": lead_summary.priorityScore,
                    "snapshotPipelineStatus": lead_summary.pipelineStatus.value,
                    "targetStatus": CampaignTargetStatus.PENDING.value,
                    "inclusionReason": reasons,
                },
            )
            target["lead"] = lead
            targets.append(CampaignTarget.model_validate(target))
            await self.repository.create_event(
                campaign_id=object_id,
                lead_id=lead_id,
                event_type="target_selected",
                payload={"leadName": lead_summary.name, "reasons": reasons, "selectedBy": current_user.username},
            )
        return CampaignTargetSelectionResponse(
            campaignId=campaign_id,
            selectedCount=len(targets),
            skippedCount=skipped_count,
            targets=targets,
        )

    async def list_targets(self, campaign_id: str) -> list[CampaignTarget]:
        object_id = parse_object_id(campaign_id)
        await self._ensure_campaign(object_id)
        targets = await self.repository.list_targets(object_id)
        return [CampaignTarget.model_validate(target) for target in await self._hydrate_targets(targets)]

    async def list_drafts(self, campaign_id: str) -> list[MessageDraft]:
        object_id = parse_object_id(campaign_id)
        await self._ensure_campaign(object_id)
        drafts = await self.repository.list_drafts(object_id)
        return [MessageDraft.model_validate(draft) for draft in await self._hydrate_drafts(drafts)]

    async def generate_drafts(
        self,
        campaign_id: str,
        current_user: UserResponse,
    ) -> list[MessageDraft]:
        campaign = Campaign.model_validate(await self._get_campaign_document(campaign_id))
        object_id = parse_object_id(campaign_id)
        template = await self.repository.get_default_template(campaign.channel.value)
        if template is None:
            template = await self.repository.create_template(DEFAULT_TEMPLATE.model_dump())
        template_id = parse_object_id(template["id"])
        targets = await self.repository.list_targets(object_id)
        created: list[dict[str, Any]] = []
        for target in targets:
            if target["targetStatus"] in {CampaignTargetStatus.IGNORED.value, CampaignTargetStatus.FAILED.value}:
                continue
            lead_id = parse_object_id(target["leadId"])
            lead = await self.repository.get_lead(lead_id)
            if lead is None:
                continue
            feature_snapshot = await self.repository.get_latest_feature_snapshot(lead_id)
            variables = self._draft_variables(LeadSummary.model_validate(lead), feature_snapshot)
            draft = await self.repository.create_or_update_draft(
                campaign_id=object_id,
                lead_id=lead_id,
                template_id=template_id,
                document={
                    "channel": campaign.channel.value,
                    "subject": self._render_template(template.get("subjectTemplate"), variables),
                    "body": self._render_template(template["bodyTemplate"], variables),
                    "draftStatus": MessageDraftStatus.GENERATED.value,
                    "generationReason": self._generation_reasons(variables),
                },
            )
            await self.repository.update_target_status(
                campaign_id=object_id,
                lead_id=lead_id,
                target_status=CampaignTargetStatus.DRAFTED.value,
            )
            await self.repository.create_event(
                campaign_id=object_id,
                lead_id=lead_id,
                event_type="draft_generated",
                payload={"draftId": draft["id"], "generatedBy": current_user.username},
            )
            created.append(draft)
        return [MessageDraft.model_validate(draft) for draft in await self._hydrate_drafts(created)]

    async def update_draft(
        self,
        draft_id: str,
        payload: MessageDraftUpdate,
        current_user: UserResponse,
    ) -> MessageDraft:
        object_id = parse_object_id(draft_id)
        draft = await self._get_draft_document(object_id)
        update_data = payload.model_dump(exclude_unset=True)
        updated = await self.repository.update_draft(object_id, update_data)
        await self.repository.create_event(
            campaign_id=parse_object_id(draft["campaignId"]),
            lead_id=parse_object_id(draft["leadId"]),
            event_type="draft_updated",
            payload={"draftId": draft_id, "updatedBy": current_user.username, "changedFields": sorted(update_data.keys())},
        )
        return MessageDraft.model_validate((await self._hydrate_drafts([updated]))[0])

    async def approve_draft(self, draft_id: str, current_user: UserResponse) -> MessageDraft:
        return await self._set_draft_decision(
            draft_id=draft_id,
            current_user=current_user,
            draft_status=MessageDraftStatus.APPROVED,
            target_status=CampaignTargetStatus.APPROVED,
            event_type="draft_approved",
            activity_type="campaign_draft_approved",
            description="Campaign message draft approved for outreach preparation.",
        )

    async def reject_draft(self, draft_id: str, current_user: UserResponse) -> MessageDraft:
        return await self._set_draft_decision(
            draft_id=draft_id,
            current_user=current_user,
            draft_status=MessageDraftStatus.REJECTED,
            target_status=CampaignTargetStatus.IGNORED,
            event_type="draft_rejected",
            activity_type="campaign_draft_rejected",
            description="Campaign message draft rejected during review.",
        )

    async def list_templates(self) -> list[MessageTemplate]:
        templates = await self.repository.list_templates()
        return [MessageTemplate.model_validate(template) for template in templates]

    async def create_template(self, payload: MessageTemplateCreate) -> MessageTemplate:
        template = await self.repository.create_template(payload.model_dump())
        return MessageTemplate.model_validate(template)

    async def list_events(self, campaign_id: str) -> list[CampaignEvent]:
        object_id = parse_object_id(campaign_id)
        await self._ensure_campaign(object_id)
        events = await self.repository.list_events(object_id)
        return [CampaignEvent.model_validate(event) for event in events]

    async def _set_draft_decision(
        self,
        *,
        draft_id: str,
        current_user: UserResponse,
        draft_status: MessageDraftStatus,
        target_status: CampaignTargetStatus,
        event_type: str,
        activity_type: str,
        description: str,
    ) -> MessageDraft:
        object_id = parse_object_id(draft_id)
        draft = await self._get_draft_document(object_id)
        campaign_id = parse_object_id(draft["campaignId"])
        lead_id = parse_object_id(draft["leadId"])
        updated = await self.repository.update_draft(object_id, {"draftStatus": draft_status.value})
        await self.repository.update_target_status(
            campaign_id=campaign_id,
            lead_id=lead_id,
            target_status=target_status.value,
        )
        await self.repository.create_event(
            campaign_id=campaign_id,
            lead_id=lead_id,
            event_type=event_type,
            payload={"draftId": draft_id, "reviewedBy": current_user.username},
        )
        await self.repository.create_lead_activity(
            lead_id=lead_id,
            activity_type=activity_type,
            channel=draft["channel"],
            description=description,
            performed_by=current_user.username,
        )
        return MessageDraft.model_validate((await self._hydrate_drafts([updated]))[0])

    async def _get_campaign_document(self, campaign_id: str) -> dict[str, Any]:
        object_id = parse_object_id(campaign_id)
        return await self._ensure_campaign(object_id)

    async def _ensure_campaign(self, campaign_id: ObjectId) -> dict[str, Any]:
        campaign = await self.repository.get_campaign(campaign_id)
        if campaign is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
        return campaign

    async def _get_draft_document(self, draft_id: ObjectId) -> dict[str, Any]:
        draft = await self.repository.get_draft(draft_id)
        if draft is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
        return draft

    async def _hydrate_targets(self, targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        leads = await self.repository.get_leads_by_ids(
            [parse_object_id(target["leadId"]) for target in targets if ObjectId.is_valid(target["leadId"])]
        )
        for target in targets:
            target["lead"] = leads.get(target["leadId"])
        return targets

    async def _hydrate_drafts(self, drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        leads = await self.repository.get_leads_by_ids(
            [parse_object_id(draft["leadId"]) for draft in drafts if ObjectId.is_valid(draft["leadId"])]
        )
        template_ids = [parse_object_id(draft["templateId"]) for draft in drafts if ObjectId.is_valid(draft["templateId"])]
        templates: dict[str, dict[str, Any]] = {}
        for template_id in template_ids:
            template = await self.repository.get_template(template_id)
            if template:
                templates[template["id"]] = template
        for draft in drafts:
            draft["lead"] = leads.get(draft["leadId"])
            draft["template"] = templates.get(draft["templateId"])
        return drafts

    def _is_commercially_eligible(self, lead: LeadSummary, criteria: CampaignTargetCriteria) -> bool:
        threshold = criteria.minPriorityScore if criteria.minPriorityScore is not None else 70
        return lead.pipelineStatus in COMMERCIAL_STATUSES or lead.priorityScore >= threshold

    def _target_reasons(self, lead: LeadSummary, criteria: CampaignTargetCriteria) -> list[str]:
        reasons: list[str] = []
        if lead.pipelineStatus in COMMERCIAL_STATUSES:
            reasons.append(f"Pipeline status is {lead.pipelineStatus.value}.")
        if criteria.minPriorityScore is not None and lead.priorityScore >= criteria.minPriorityScore:
            reasons.append(f"Priority score {lead.priorityScore} meets threshold {criteria.minPriorityScore}.")
        if criteria.city and lead.city:
            reasons.append(f"City matches {lead.city}.")
        if criteria.district and lead.district:
            reasons.append(f"District matches {lead.district}.")
        if lead.modelScored:
            reasons.append("Lead has live model scoring.")
        if lead.lastEnrichedAt:
            reasons.append("Lead has enrichment evidence.")
        return reasons or ["Lead matches campaign criteria."]

    def _draft_variables(self, lead: LeadSummary, feature_snapshot: dict[str, Any] | None) -> dict[str, str]:
        features = feature_snapshot.get("features", {}) if feature_snapshot else {}
        derived = feature_snapshot.get("derivedSignals", {}) if feature_snapshot else {}
        booking_hint = str(features.get("bookingProviderHint") or "no booking provider detected")
        reason_parts = [
            f"{lead.name}",
            f"score {lead.priorityScore}",
            f"status {lead.pipelineStatus.value}",
        ]
        if derived.get("digitalMaturity"):
            reason_parts.append(f"digital maturity: {derived['digitalMaturity']}")
        if features.get("hasBookingLink"):
            reason_parts.append(f"booking signal: {booking_hint}")
        return {
            "leadName": lead.name,
            "district": lead.district or "your area",
            "city": lead.city or "your city",
            "priorityScore": str(lead.priorityScore),
            "pipelineStatus": lead.pipelineStatus.value,
            "website": lead.website or "no website captured",
            "bookingHint": booking_hint,
            "reasonSummary": ", ".join(reason_parts),
        }

    def _generation_reasons(self, variables: dict[str, str]) -> list[str]:
        return [
            f"Lead score: {variables['priorityScore']}.",
            f"Pipeline status: {variables['pipelineStatus']}.",
            f"Booking hint: {variables['bookingHint']}.",
        ]

    def _render_template(self, template: str | None, variables: dict[str, str]) -> str | None:
        if template is None:
            return None
        rendered = template
        for key, value in variables.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", value)
            rendered = rendered.replace(f"{{{{ {key} }}}}", value)
        return re.sub(r"{{\s*[\w]+\s*}}", "", rendered).strip()


def get_campaign_service(
    database: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
) -> CampaignService:
    return CampaignService(CampaignRepository(database))
