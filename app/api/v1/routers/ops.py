from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.schemas.jobs import OpsSummaryResponse
from app.services.ops import OpsService, get_ops_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/summary", response_model=OpsSummaryResponse)
async def ops_summary(
    service: Annotated[OpsService, Depends(get_ops_service)],
) -> OpsSummaryResponse:
    return await service.get_summary()
