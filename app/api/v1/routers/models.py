from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.schemas.auth import UserResponse
from app.schemas.models import (
    ActiveModelConfig,
    ActiveModelUpdateRequest,
    ModelRegistryEntry,
    ModelTrainRequest,
    ModelTrainResponse,
    TrainingRun,
)
from app.services.models import ModelService, get_model_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.post("/train", response_model=ModelTrainResponse)
async def train_models(
    payload: ModelTrainRequest,
    service: Annotated[ModelService, Depends(get_model_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> ModelTrainResponse:
    return await service.train(payload, current_user)


@router.get("/runs", response_model=list[TrainingRun])
async def list_training_runs(
    service: Annotated[ModelService, Depends(get_model_service)],
) -> list[TrainingRun]:
    return await service.list_runs()


@router.get("/active", response_model=list[ActiveModelConfig])
async def list_active_models(
    service: Annotated[ModelService, Depends(get_model_service)],
) -> list[ActiveModelConfig]:
    return await service.list_active_models()


@router.post("/active", response_model=ActiveModelConfig)
async def set_active_model(
    payload: ActiveModelUpdateRequest,
    service: Annotated[ModelService, Depends(get_model_service)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> ActiveModelConfig:
    return await service.set_active_model(payload, current_user)


@router.get("", response_model=list[ModelRegistryEntry])
async def list_models(
    service: Annotated[ModelService, Depends(get_model_service)],
) -> list[ModelRegistryEntry]:
    return await service.list_models()


@router.get("/{model_id}", response_model=ModelRegistryEntry)
async def get_model(
    model_id: str,
    service: Annotated[ModelService, Depends(get_model_service)],
) -> ModelRegistryEntry:
    return await service.get_model(model_id)


@router.post("/{model_id}/activate", response_model=ModelRegistryEntry)
async def activate_model(
    model_id: str,
    service: Annotated[ModelService, Depends(get_model_service)],
) -> ModelRegistryEntry:
    return await service.activate_model(model_id)
