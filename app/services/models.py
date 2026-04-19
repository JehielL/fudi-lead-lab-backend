import base64
import pickle
from datetime import UTC, datetime
from typing import Annotated, Any

from bson import ObjectId
from fastapi import Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.object_id import parse_object_id
from app.db.dependencies import get_database
from app.repositories.model_repository import ModelRepository
from app.schemas.auth import UserResponse
from app.schemas.models import (
    ModelAlgorithm,
    ModelMetric,
    ModelRegistryEntry,
    ModelTrainRequest,
    ModelTrainResponse,
    ModelType,
    TrainingRun,
)

TARGET_FIELDS: dict[ModelType, str] = {
    ModelType.NEWNESS: "newnessScore",
    ModelType.DIGITAL_GAP: "digitalGapScore",
    ModelType.FIT: "fitScore",
    ModelType.CONTACTABILITY: "contactabilityScore",
}

FEATURE_NAMES = [
    "hasWebsite",
    "hasInstagram",
    "hasFacebook",
    "hasPhone",
    "hasEmail",
    "hasContactForm",
    "hasMenuLink",
    "hasBookingLink",
    "lowContentWebsite",
    "brokenWebsiteHint",
    "socialOnlyPresenceHint",
    "openingSoonHint",
    "newOpeningHint",
    "comingSoonHint",
    "contactabilityScore",
    "priorityScore",
    "fitScore",
    "confidence",
    "textLength",
    "linkCount",
]


class ModelService:
    def __init__(self, repository: ModelRepository):
        self.repository = repository

    async def train(self, payload: ModelTrainRequest, current_user: UserResponse) -> ModelTrainResponse:
        run = await self.repository.create_training_run(
            triggered_by=current_user.username,
            metadata={"requestedAlgorithms": [algorithm.value for algorithm in payload.algorithms]},
        )
        run_id = ObjectId(run["id"])
        try:
            dataset = await self._build_dataset()
            if not dataset:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="No feature snapshots available for training.",
                )
            created_models: list[dict[str, Any]] = []
            for model_type in ModelType:
                labels = [row["labels"][model_type] for row in dataset]
                algorithms = (
                    [ModelAlgorithm.BASELINE]
                    if len(set(labels)) < 2 or len(dataset) < 6
                    else payload.algorithms
                )
                for algorithm in algorithms:
                    created_models.append(
                        await self._train_one(
                            run_id=run_id,
                            model_type=model_type,
                            algorithm=algorithm,
                            rows=dataset,
                            labels=labels,
                        )
                    )
            if payload.activateBest:
                for model_type in ModelType:
                    type_models = [model for model in created_models if model["modelType"] == model_type.value]
                    best = max(type_models, key=lambda model: float(model["metrics"].get("accuracy", 0)))
                    activated = await self.repository.activate_model(ObjectId(best["id"]), model_type.value)
                    if activated:
                        best.update(activated)
            completed = await self.repository.complete_training_run(
                run_id,
                dataset_size=len(dataset),
                feature_names=FEATURE_NAMES,
                model_ids=[model["id"] for model in created_models],
            )
            return ModelTrainResponse(
                run=TrainingRun.model_validate(completed),
                models=[ModelRegistryEntry.model_validate(model) for model in created_models],
            )
        except HTTPException:
            await self.repository.fail_training_run(run_id, "Training request could not be completed.")
            raise
        except Exception as exc:
            message = f"Training failed: {exc.__class__.__name__}."
            failed = await self.repository.fail_training_run(run_id, message)
            return ModelTrainResponse(run=TrainingRun.model_validate(failed), models=[])

    async def list_models(self) -> list[ModelRegistryEntry]:
        return [ModelRegistryEntry.model_validate(model) for model in await self.repository.list_models()]

    async def get_model(self, model_id: str) -> ModelRegistryEntry:
        document = await self.repository.get_model(parse_object_id(model_id))
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
        return ModelRegistryEntry.model_validate(document)

    async def activate_model(self, model_id: str) -> ModelRegistryEntry:
        model = await self.get_model(model_id)
        activated = await self.repository.activate_model(parse_object_id(model_id), model.modelType.value)
        return ModelRegistryEntry.model_validate(activated)

    async def list_runs(self) -> list[TrainingRun]:
        return [TrainingRun.model_validate(run) for run in await self.repository.list_training_runs()]

    async def _build_dataset(self) -> list[dict[str, Any]]:
        snapshots = await self.repository.latest_feature_snapshots()
        lead_ids = [snapshot["leadId"] for snapshot in snapshots]
        leads = await self.repository.get_leads_by_ids(lead_ids)
        leads_by_id = {str(lead["_id"]): lead for lead in leads}
        rows: list[dict[str, Any]] = []
        for snapshot in snapshots:
            lead = leads_by_id.get(str(snapshot["leadId"]))
            if not lead:
                continue
            features = snapshot.get("features", {})
            score_breakdown = lead.get("scoreBreakdown", {})
            rows.append(
                {
                    "leadId": str(lead["_id"]),
                    "x": self._feature_vector(features, lead),
                    "labels": {
                        model_type: 1 if int(score_breakdown.get(score_field, 0) or 0) >= 60 else 0
                        for model_type, score_field in TARGET_FIELDS.items()
                    },
                }
            )
        return rows

    async def _train_one(
        self,
        *,
        run_id: ObjectId,
        model_type: ModelType,
        algorithm: ModelAlgorithm,
        rows: list[dict[str, Any]],
        labels: list[int],
    ) -> dict[str, Any]:
        x = [row["x"] for row in rows]
        positive_count = sum(labels)
        negative_count = len(labels) - positive_count
        artifact: dict[str, Any]
        metrics: dict[str, float | int | str | None]
        if algorithm == ModelAlgorithm.BASELINE:
            majority = 1 if positive_count >= negative_count else 0
            metrics = {
                "accuracy": round(max(positive_count, negative_count) / max(len(labels), 1), 4),
                "precision": None,
                "recall": None,
                "f1": None,
                "mode": "baseline_insufficient_data",
            }
            artifact = {"kind": "baseline", "prediction": majority}
        else:
            model, metrics = self._fit_sklearn_model(x, labels, algorithm)
            artifact = {
                "kind": "sklearn_pickle_base64",
                "payload": base64.b64encode(pickle.dumps(model)).decode("ascii"),
            }
        now = datetime.now(UTC)
        version = f"{model_type.value}-{algorithm.value}-{now.strftime('%Y%m%d%H%M%S')}"
        model_document = {
            "modelType": model_type.value,
            "algorithm": algorithm.value,
            "version": version,
            "isActive": False,
            "status": "completed",
            "featureNames": FEATURE_NAMES,
            "sampleCount": len(rows),
            "positiveCount": positive_count,
            "negativeCount": negative_count,
            "metrics": metrics,
            "artifact": artifact,
            "trainingRunId": run_id,
            "trainedAt": now,
            "activatedAt": None,
        }
        model = await self.repository.create_model(model_document)
        await self.repository.create_metric(
            {
                "modelId": ObjectId(model["id"]),
                "trainingRunId": run_id,
                "modelType": model_type.value,
                "algorithm": algorithm.value,
                "metrics": metrics,
                "createdAt": now,
            }
        )
        return model

    def _fit_sklearn_model(
        self,
        x: list[list[float]],
        labels: list[int],
        algorithm: ModelAlgorithm,
    ) -> tuple[Any, dict[str, float | int | str | None]]:
        from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
        from sklearn.model_selection import train_test_split
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        stratify = labels if min(sum(labels), len(labels) - sum(labels)) >= 2 else None
        x_train, x_test, y_train, y_test = train_test_split(
            x,
            labels,
            test_size=0.3,
            random_state=42,
            stratify=stratify,
        )
        if algorithm == ModelAlgorithm.LOGISTIC_REGRESSION:
            model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=500))
        elif algorithm == ModelAlgorithm.RANDOM_FOREST:
            model = RandomForestClassifier(n_estimators=80, random_state=42, class_weight="balanced")
        else:
            model = HistGradientBoostingClassifier(random_state=42)
        model.fit(x_train, y_train)
        predictions = model.predict(x_test)
        return model, {
            "accuracy": round(float(accuracy_score(y_test, predictions)), 4),
            "precision": round(float(precision_score(y_test, predictions, zero_division=0)), 4),
            "recall": round(float(recall_score(y_test, predictions, zero_division=0)), 4),
            "f1": round(float(f1_score(y_test, predictions, zero_division=0)), 4),
            "mode": "sklearn_train_test_split",
        }

    def _feature_vector(self, features: dict[str, Any], lead: dict[str, Any]) -> list[float]:
        values: dict[str, Any] = {
            **features,
            "priorityScore": lead.get("priorityScore"),
            "fitScore": lead.get("fitScore"),
            "confidence": lead.get("confidence"),
        }
        vector: list[float] = []
        for name in FEATURE_NAMES:
            value = values.get(name)
            if isinstance(value, bool):
                vector.append(1.0 if value else 0.0)
            elif isinstance(value, (int, float)):
                vector.append(float(value))
            else:
                vector.append(0.0)
        return vector


def get_model_service(
    database: Annotated[AsyncIOMotorDatabase, Depends(get_database)],
) -> ModelService:
    return ModelService(ModelRepository(database))
