from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.security import get_current_user
from app.schemas.auth import UserResponse
from app.schemas.outreach import (
    CampaignSendResponse,
    OutboxDetail,
    OutboxMessage,
    OutboxStatus,
    QueueDraftRequest,
    ScheduleCampaignRequest,
    SuppressionCreate,
    SuppressionEntry,
)
from app.services.outreach import OutreachService, get_outreach_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.post("/campaigns/{campaign_id}/send", response_model=CampaignSendResponse)
async def send_campaign(
    campaign_id: str,
    service: Annotated[OutreachService, Depends(get_outreach_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> CampaignSendResponse:
    return await service.send_campaign(campaign_id, current_user)


@router.post("/campaigns/{campaign_id}/schedule", response_model=CampaignSendResponse)
async def schedule_campaign(
    campaign_id: str,
    payload: ScheduleCampaignRequest,
    service: Annotated[OutreachService, Depends(get_outreach_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> CampaignSendResponse:
    return await service.schedule_campaign(campaign_id, payload, current_user)


@router.get("/campaigns/{campaign_id}/outbox", response_model=list[OutboxMessage])
async def list_campaign_outbox(
    campaign_id: str,
    service: Annotated[OutreachService, Depends(get_outreach_service)],
) -> list[OutboxMessage]:
    return await service.list_campaign_outbox(campaign_id)


@router.post("/drafts/{draft_id}/queue", response_model=OutboxMessage)
async def queue_draft(
    draft_id: str,
    payload: QueueDraftRequest,
    service: Annotated[OutreachService, Depends(get_outreach_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> OutboxMessage:
    return await service.queue_draft(draft_id, payload, current_user)


@router.post("/drafts/{draft_id}/send", response_model=OutboxMessage)
async def send_draft(
    draft_id: str,
    service: Annotated[OutreachService, Depends(get_outreach_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> OutboxMessage:
    return await service.send_draft(draft_id, current_user)


@router.get("/outbox", response_model=list[OutboxMessage])
async def list_outbox(
    service: Annotated[OutreachService, Depends(get_outreach_service)],
    outboxStatus: Annotated[OutboxStatus | None, Query(alias="status")] = None,
) -> list[OutboxMessage]:
    return await service.list_outbox(outboxStatus)


@router.get("/outbox/{outbox_id}", response_model=OutboxDetail)
async def get_outbox(
    outbox_id: str,
    service: Annotated[OutreachService, Depends(get_outreach_service)],
) -> OutboxDetail:
    return await service.get_outbox_detail(outbox_id)


@router.post("/outbox/{outbox_id}/retry", response_model=OutboxMessage)
async def retry_outbox(
    outbox_id: str,
    service: Annotated[OutreachService, Depends(get_outreach_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> OutboxMessage:
    return await service.retry_outbox(outbox_id, current_user)


@router.post("/outbox/{outbox_id}/cancel", response_model=OutboxMessage)
async def cancel_outbox(
    outbox_id: str,
    service: Annotated[OutreachService, Depends(get_outreach_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> OutboxMessage:
    return await service.cancel_outbox(outbox_id, current_user)


@router.get("/suppressions", response_model=list[SuppressionEntry])
async def list_suppressions(
    service: Annotated[OutreachService, Depends(get_outreach_service)],
) -> list[SuppressionEntry]:
    return await service.list_suppressions()


@router.post("/suppressions", response_model=SuppressionEntry, status_code=status.HTTP_201_CREATED)
async def create_suppression(
    payload: SuppressionCreate,
    service: Annotated[OutreachService, Depends(get_outreach_service)],
) -> SuppressionEntry:
    return await service.create_suppression(payload)


@router.delete("/suppressions/{suppression_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_suppression(
    suppression_id: str,
    service: Annotated[OutreachService, Depends(get_outreach_service)],
) -> Response:
    await service.delete_suppression(suppression_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
