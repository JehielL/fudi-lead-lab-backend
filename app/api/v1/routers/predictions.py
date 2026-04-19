from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.schemas.models import PredictionRun
from app.services.models import ModelService, get_model_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/runs", response_model=list[PredictionRun])
async def list_prediction_runs(
    service: Annotated[ModelService, Depends(get_model_service)],
) -> list[PredictionRun]:
    return await service.list_prediction_runs()
