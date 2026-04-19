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
    ActiveModelConfig,
    ActiveModelUpdateRequest,
    BatchPredictionRequest,
    BatchPredictionResponse,
    LeadPredictionResponse,
    ModelAlgorithm,
    ModelMetric,
    ModelRegistryEntry,
    ModelTrainRequest,
    ModelTrainResponse,
    ModelType,
    PredictionRun,
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
        await self.repository.upsert_active_model_config(
            model_type=model.modelType.value,
            model_id=parse_object_id(model_id),
            model_version=model.version,
            updated_by="system",
        )
        return ModelRegistryEntry.model_validate(activated)

    async def list_active_models(self) -> list[ActiveModelConfig]:
        configs = await self.repository.list_active_model_config()
        result: list[ActiveModelConfig] = []
        for config in configs:
            model = await self.repository.get_model(ObjectId(config["modelId"]))
            config["model"] = model
            result.append(ActiveModelConfig.model_validate(config))
        return result

    async def set_active_model(
        self,
        payload: ActiveModelUpdateRequest,
        current_user: UserResponse,
    ) -> ActiveModelConfig:
        model = await self.get_model(payload.modelId)
        if model.modelType != payload.modelType:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Model type does not match requested active slot.",
            )
        activated = await self.repository.activate_model(parse_object_id(payload.modelId), payload.modelType.value)
        config = await self.repository.upsert_active_model_config(
            model_type=payload.modelType.value,
            model_id=parse_object_id(payload.modelId),
            model_version=model.version,
            updated_by=current_user.username,
        )
        config["model"] = activated
        return ActiveModelConfig.model_validate(config)

    async def list_runs(self) -> list[TrainingRun]:
        return [TrainingRun.model_validate(run) for run in await self.repository.list_training_runs()]

    async def predict_lead(
        self,
        lead_id: str,
        current_user: UserResponse,
        trigger_type: str = "manual",
    ) -> LeadPredictionResponse:
        _ = current_user
        object_id = parse_object_id(lead_id)
        lead = await self.repository.get_lead(object_id)
        if lead is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        feature_snapshot = await self.repository.get_latest_feature_snapshot(object_id)
        features = feature_snapshot.get("features", {}) if feature_snapshot else {}
        feature_snapshot_id = feature_snapshot["id"] if feature_snapshot else None
        vector = self._feature_vector(features, lead)
        runs: list[dict[str, Any]] = []
        scores: dict[ModelType, int] = {}
        confidences: list[int] = []
        metadata: dict[str, Any] = {"triggerType": trigger_type, "models": {}}

        for model_type in ModelType:
            model = await self.repository.get_active_model_for_type(model_type.value)
            if model is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"No active model configured for {model_type.value}.",
                )
            prediction, confidence = self._predict_with_model(model, vector)
            explanations = self._prediction_explanations(model_type, prediction, model, features)
            runs.append(
                await self.repository.create_prediction_run(
                    {
                        "leadId": object_id,
                        "modelId": ObjectId(model["id"]),
                        "modelType": model_type.value,
                        "modelVersion": model["version"],
                        "inputFeatureSnapshotId": ObjectId(feature_snapshot_id) if feature_snapshot_id else None,
                        "prediction": prediction,
                        "confidence": confidence,
                        "explanations": explanations,
                        "createdAt": datetime.now(UTC),
                        "triggerType": trigger_type,
                    }
                )
            )
            scores[model_type] = prediction
            confidences.append(confidence)
            metadata["models"][model_type.value] = {
                "modelId": model["id"],
                "modelVersion": model["version"],
                "algorithm": model["algorithm"],
            }

        priority_score = round(
            scores[ModelType.NEWNESS] * 0.22
            + scores[ModelType.DIGITAL_GAP] * 0.33
            + scores[ModelType.FIT] * 0.27
            + scores[ModelType.CONTACTABILITY] * 0.18
        )
        confidence = round(sum(confidences) / len(confidences))
        score_breakdown = {
            "newnessScore": scores[ModelType.NEWNESS],
            "digitalGapScore": scores[ModelType.DIGITAL_GAP],
            "fitScore": scores[ModelType.FIT],
            "contactabilityScore": scores[ModelType.CONTACTABILITY],
            "priorityScore": priority_score,
            "explanation": [explanation for run in runs for explanation in run["explanations"]],
        }
        await self.repository.update_lead_score_from_prediction(
            object_id,
            score_breakdown=score_breakdown,
            confidence=confidence,
            metadata=metadata,
            trigger_type=trigger_type,
        )
        return LeadPredictionResponse(
            leadId=lead_id,
            scoreBreakdown=score_breakdown,
            priorityScore=priority_score,
            confidence=confidence,
            predictionRuns=[PredictionRun.model_validate(run) for run in runs],
        )

    async def predict_batch(
        self,
        payload: BatchPredictionRequest,
        current_user: UserResponse,
    ) -> BatchPredictionResponse:
        if payload.leadIds:
            lead_ids = payload.leadIds[: payload.limit]
        else:
            lead_ids = [str(lead["_id"]) for lead in await self.repository.list_predictable_leads(payload.limit)]
        results: list[LeadPredictionResponse] = []
        for lead_id in lead_ids:
            results.append(await self.predict_lead(lead_id, current_user, trigger_type="batch"))
        return BatchPredictionResponse(predictedCount=len(results), results=results)

    async def list_prediction_runs(self) -> list[PredictionRun]:
        return [PredictionRun.model_validate(run) for run in await self.repository.list_prediction_runs()]

    async def list_lead_prediction_runs(self, lead_id: str) -> list[PredictionRun]:
        return [
            PredictionRun.model_validate(run)
            for run in await self.repository.list_lead_prediction_runs(parse_object_id(lead_id))
        ]

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

    def _predict_with_model(self, model_document: dict[str, Any], vector: list[float]) -> tuple[int, int]:
        artifact = model_document.get("artifact") or {}
        metrics = model_document.get("metrics") or {}
        if artifact.get("kind") == "baseline":
            prediction = 75 if int(artifact.get("prediction") or 0) else 35
            confidence = round(float(metrics.get("accuracy") or 0.6) * 100)
            return prediction, max(1, min(confidence, 100))
        model = pickle.loads(base64.b64decode(artifact["payload"]))
        if hasattr(model, "predict_proba"):
            probability = float(model.predict_proba([vector])[0][1])
            prediction = round(probability * 100)
            confidence = round((0.5 + abs(probability - 0.5)) * 100)
            return prediction, max(1, min(confidence, 100))
        predicted_class = int(model.predict([vector])[0])
        return (75 if predicted_class else 35), 65

    def _prediction_explanations(
        self,
        model_type: ModelType,
        prediction: int,
        model_document: dict[str, Any],
        features: dict[str, Any],
    ) -> list[str]:
        explanations = [
            f"{model_type.value} scored {prediction} by {model_document['version']}.",
        ]
        if features.get("brokenWebsiteHint"):
            explanations.append("Broken website signal influenced model scoring.")
        if features.get("lowContentWebsite"):
            explanations.append("Low content signal influenced model scoring.")
        if features.get("hasBookingLink"):
            explanations.append("Booking flow signal is present.")
        if features.get("hasEmail") or features.get("hasPhone"):
            explanations.append("Direct contact signal is present.")
        return explanations[:4]

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
