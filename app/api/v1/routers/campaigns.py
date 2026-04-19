from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.security import get_current_user
from app.schemas.auth import UserResponse
from app.schemas.campaigns import (
    Campaign,
    CampaignCreate,
    CampaignEvent,
    CampaignTarget,
    CampaignTargetSelectionResponse,
    CampaignUpdate,
    MessageDraft,
    MessageDraftUpdate,
    MessageTemplate,
    MessageTemplateCreate,
)
from app.services.campaigns import CampaignService, get_campaign_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/campaigns", response_model=list[Campaign])
async def list_campaigns(
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> list[Campaign]:
    return await service.list_campaigns()


@router.post("/campaigns", response_model=Campaign, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate,
    service: Annotated[CampaignService, Depends(get_campaign_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> Campaign:
    return await service.create_campaign(payload, current_user)


@router.get("/campaigns/{campaign_id}", response_model=Campaign)
async def get_campaign(
    campaign_id: str,
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> Campaign:
    return await service.get_campaign(campaign_id)


@router.patch("/campaigns/{campaign_id}", response_model=Campaign)
async def update_campaign(
    campaign_id: str,
    payload: CampaignUpdate,
    service: Annotated[CampaignService, Depends(get_campaign_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> Campaign:
    return await service.update_campaign(campaign_id, payload, current_user)


@router.get("/campaigns/{campaign_id}/targets", response_model=list[CampaignTarget])
async def list_campaign_targets(
    campaign_id: str,
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> list[CampaignTarget]:
    return await service.list_targets(campaign_id)


@router.post("/campaigns/{campaign_id}/targets/select", response_model=CampaignTargetSelectionResponse)
async def select_campaign_targets(
    campaign_id: str,
    service: Annotated[CampaignService, Depends(get_campaign_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> CampaignTargetSelectionResponse:
    return await service.select_targets(campaign_id, current_user)


@router.get("/campaigns/{campaign_id}/drafts", response_model=list[MessageDraft])
async def list_campaign_drafts(
    campaign_id: str,
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> list[MessageDraft]:
    return await service.list_drafts(campaign_id)


@router.post("/campaigns/{campaign_id}/drafts/generate", response_model=list[MessageDraft])
async def generate_campaign_drafts(
    campaign_id: str,
    service: Annotated[CampaignService, Depends(get_campaign_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> list[MessageDraft]:
    return await service.generate_drafts(campaign_id, current_user)


@router.get("/campaigns/{campaign_id}/events", response_model=list[CampaignEvent])
async def list_campaign_events(
    campaign_id: str,
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> list[CampaignEvent]:
    return await service.list_events(campaign_id)


@router.patch("/drafts/{draft_id}", response_model=MessageDraft)
async def update_draft(
    draft_id: str,
    payload: MessageDraftUpdate,
    service: Annotated[CampaignService, Depends(get_campaign_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> MessageDraft:
    return await service.update_draft(draft_id, payload, current_user)


@router.post("/drafts/{draft_id}/approve", response_model=MessageDraft)
async def approve_draft(
    draft_id: str,
    service: Annotated[CampaignService, Depends(get_campaign_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> MessageDraft:
    return await service.approve_draft(draft_id, current_user)


@router.post("/drafts/{draft_id}/reject", response_model=MessageDraft)
async def reject_draft(
    draft_id: str,
    service: Annotated[CampaignService, Depends(get_campaign_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> MessageDraft:
    return await service.reject_draft(draft_id, current_user)


@router.get("/templates", response_model=list[MessageTemplate])
async def list_templates(
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> list[MessageTemplate]:
    return await service.list_templates()


@router.post("/templates", response_model=MessageTemplate, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: MessageTemplateCreate,
    service: Annotated[CampaignService, Depends(get_campaign_service)],
) -> MessageTemplate:
    return await service.create_template(payload)
