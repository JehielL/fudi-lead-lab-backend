from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ModelType(StrEnum):
    NEWNESS = "newness"
    DIGITAL_GAP = "digital_gap"
    FIT = "fit"
    CONTACTABILITY = "contactability"


class ModelAlgorithm(StrEnum):
    LOGISTIC_REGRESSION = "LogisticRegression"
    RANDOM_FOREST = "RandomForest"
    HIST_GRADIENT_BOOSTING = "HistGradientBoosting"
    BASELINE = "Baseline"


class TrainingStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ModelMetric(BaseModel):
    id: str
    modelId: str
    trainingRunId: str
    modelType: ModelType
    algorithm: ModelAlgorithm
    metrics: dict[str, float | int | str | None] = Field(default_factory=dict)
    createdAt: datetime


class ModelRegistryEntry(BaseModel):
    id: str
    modelType: ModelType
    algorithm: ModelAlgorithm
    version: str
    isActive: bool = False
    status: TrainingStatus = TrainingStatus.COMPLETED
    featureNames: list[str] = Field(default_factory=list)
    sampleCount: int = 0
    positiveCount: int = 0
    negativeCount: int = 0
    metrics: dict[str, float | int | str | None] = Field(default_factory=dict)
    artifact: dict[str, Any] = Field(default_factory=dict)
    trainingRunId: str
    trainedAt: datetime
    activatedAt: datetime | None = None


class TrainingRun(BaseModel):
    id: str
    status: TrainingStatus
    startedAt: datetime
    finishedAt: datetime | None = None
    triggeredBy: str
    datasetSize: int = 0
    featureNames: list[str] = Field(default_factory=list)
    modelIds: list[str] = Field(default_factory=list)
    errorMessage: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelTrainRequest(BaseModel):
    activateBest: bool = True
    algorithms: list[ModelAlgorithm] = Field(
        default_factory=lambda: [
            ModelAlgorithm.LOGISTIC_REGRESSION,
            ModelAlgorithm.RANDOM_FOREST,
            ModelAlgorithm.HIST_GRADIENT_BOOSTING,
        ]
    )


class ModelTrainResponse(BaseModel):
    run: TrainingRun
    models: list[ModelRegistryEntry]
