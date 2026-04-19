from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING

from app.core.object_id import object_id_to_str


def serialize_model_document(document: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(document)
    serialized["id"] = object_id_to_str(serialized.pop("_id", None))
    for key in ("modelId", "trainingRunId", "leadId", "inputFeatureSnapshotId"):
        if key in serialized and serialized[key] is not None:
            serialized[key] = object_id_to_str(serialized[key])
    if "modelIds" in serialized:
        serialized["modelIds"] = [object_id_to_str(value) for value in serialized.get("modelIds", [])]
    return serialized


class ModelRepository:
    def __init__(self, database: AsyncIOMotorDatabase):
        self.leads = database.leads
        self.feature_snapshots = database.feature_snapshots
        self.model_registry = database.model_registry
        self.training_runs = database.training_runs
        self.model_metrics = database.model_metrics
        self.prediction_runs = database.prediction_runs
        self.active_model_config = database.active_model_config

    async def latest_feature_snapshots(self, limit: int = 2000) -> list[dict[str, Any]]:
        cursor = self.feature_snapshots.find({}).sort("createdAt", DESCENDING).limit(limit)
        latest_by_lead: dict[str, dict[str, Any]] = {}
        async for document in cursor:
            lead_id = str(document.get("leadId"))
            latest_by_lead.setdefault(lead_id, document)
        return list(latest_by_lead.values())

    async def get_leads_by_ids(self, lead_ids: list[ObjectId]) -> list[dict[str, Any]]:
        cursor = self.leads.find({"_id": {"$in": lead_ids}, "isActive": {"$ne": False}})
        return [document async for document in cursor]

    async def create_training_run(self, *, triggered_by: str, metadata: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC)
        document = {
            "status": "running",
            "startedAt": now,
            "finishedAt": None,
            "triggeredBy": triggered_by,
            "datasetSize": 0,
            "featureNames": [],
            "modelIds": [],
            "errorMessage": None,
            "metadata": metadata,
        }
        result = await self.training_runs.insert_one(document)
        created = await self.training_runs.find_one({"_id": result.inserted_id})
        return serialize_model_document(created)

    async def complete_training_run(
        self,
        run_id: ObjectId,
        *,
        dataset_size: int,
        feature_names: list[str],
        model_ids: list[str],
    ) -> dict[str, Any]:
        await self.training_runs.update_one(
            {"_id": run_id},
            {
                "$set": {
                    "status": "completed",
                    "finishedAt": datetime.now(UTC),
                    "datasetSize": dataset_size,
                    "featureNames": feature_names,
                    "modelIds": [ObjectId(model_id) for model_id in model_ids if ObjectId.is_valid(model_id)],
                }
            },
        )
        updated = await self.training_runs.find_one({"_id": run_id})
        return serialize_model_document(updated)

    async def fail_training_run(self, run_id: ObjectId, error_message: str) -> dict[str, Any]:
        await self.training_runs.update_one(
            {"_id": run_id},
            {
                "$set": {
                    "status": "failed",
                    "finishedAt": datetime.now(UTC),
                    "errorMessage": error_message,
                }
            },
        )
        updated = await self.training_runs.find_one({"_id": run_id})
        return serialize_model_document(updated)

    async def create_model(self, document: dict[str, Any]) -> dict[str, Any]:
        result = await self.model_registry.insert_one(document)
        created = await self.model_registry.find_one({"_id": result.inserted_id})
        return serialize_model_document(created)

    async def create_metric(self, document: dict[str, Any]) -> dict[str, Any]:
        result = await self.model_metrics.insert_one(document)
        created = await self.model_metrics.find_one({"_id": result.inserted_id})
        return serialize_model_document(created)

    async def list_models(self, limit: int = 100) -> list[dict[str, Any]]:
        cursor = self.model_registry.find({}).sort("trainedAt", DESCENDING).limit(limit)
        return [serialize_model_document(document) async for document in cursor]

    async def get_model(self, model_id: ObjectId) -> dict[str, Any] | None:
        document = await self.model_registry.find_one({"_id": model_id})
        return serialize_model_document(document) if document else None

    async def get_latest_feature_snapshot(self, lead_id: ObjectId) -> dict[str, Any] | None:
        document = await self.feature_snapshots.find_one({"leadId": lead_id}, sort=[("createdAt", DESCENDING)])
        return serialize_model_document(document) if document else None

    async def get_lead(self, lead_id: ObjectId) -> dict[str, Any] | None:
        return await self.leads.find_one({"_id": lead_id})

    async def list_predictable_leads(self, limit: int = 50) -> list[dict[str, Any]]:
        cursor = self.leads.find({"isActive": {"$ne": False}, "isDiscarded": {"$ne": True}}).sort("updatedAt", DESCENDING).limit(limit)
        return [document async for document in cursor]

    async def list_training_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        cursor = self.training_runs.find({}).sort("startedAt", DESCENDING).limit(limit)
        return [serialize_model_document(document) async for document in cursor]

    async def activate_model(self, model_id: ObjectId, model_type: str) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        await self.model_registry.update_many({"modelType": model_type}, {"$set": {"isActive": False}})
        await self.model_registry.update_one(
            {"_id": model_id},
            {"$set": {"isActive": True, "activatedAt": now}},
        )
        return await self.get_model(model_id)

    async def upsert_active_model_config(
        self,
        *,
        model_type: str,
        model_id: ObjectId,
        model_version: str,
        updated_by: str,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        await self.active_model_config.update_one(
            {"modelType": model_type},
            {
                "$set": {
                    "modelType": model_type,
                    "modelId": model_id,
                    "modelVersion": model_version,
                    "updatedAt": now,
                    "updatedBy": updated_by,
                }
            },
            upsert=True,
        )
        document = await self.active_model_config.find_one({"modelType": model_type})
        return serialize_model_document(document)

    async def list_active_model_config(self) -> list[dict[str, Any]]:
        configured = [serialize_model_document(document) async for document in self.active_model_config.find({})]
        configured_types = {document["modelType"] for document in configured}
        cursor = self.model_registry.find({"isActive": True})
        async for model in cursor:
            if model["modelType"] in configured_types:
                continue
            configured.append(
                {
                    "id": str(model["_id"]),
                    "modelType": model["modelType"],
                    "modelId": str(model["_id"]),
                    "modelVersion": model["version"],
                    "updatedAt": model.get("activatedAt") or model.get("trainedAt"),
                    "updatedBy": "system",
                }
            )
        return configured

    async def get_active_model_for_type(self, model_type: str) -> dict[str, Any] | None:
        config = await self.active_model_config.find_one({"modelType": model_type})
        if config and config.get("modelId"):
            model = await self.model_registry.find_one({"_id": config["modelId"]})
            if model:
                return serialize_model_document(model)
        model = await self.model_registry.find_one({"modelType": model_type, "isActive": True}, sort=[("activatedAt", DESCENDING)])
        return serialize_model_document(model) if model else None

    async def create_prediction_run(self, document: dict[str, Any]) -> dict[str, Any]:
        result = await self.prediction_runs.insert_one(document)
        created = await self.prediction_runs.find_one({"_id": result.inserted_id})
        return serialize_model_document(created)

    async def list_prediction_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        cursor = self.prediction_runs.find({}).sort("createdAt", DESCENDING).limit(limit)
        return [serialize_model_document(document) async for document in cursor]

    async def list_lead_prediction_runs(self, lead_id: ObjectId, limit: int = 50) -> list[dict[str, Any]]:
        cursor = self.prediction_runs.find({"leadId": lead_id}).sort("createdAt", DESCENDING).limit(limit)
        return [serialize_model_document(document) async for document in cursor]

    async def update_lead_score_from_prediction(
        self,
        lead_id: ObjectId,
        *,
        score_breakdown: dict[str, Any],
        confidence: int,
        metadata: dict[str, Any],
        trigger_type: str,
    ) -> None:
        await self.leads.update_one(
            {"_id": lead_id},
            {
                "$set": {
                    "scoreBreakdown": score_breakdown,
                    "priorityScore": score_breakdown["priorityScore"],
                    "fitScore": score_breakdown["fitScore"],
                    "confidence": confidence,
                    "scoreModelMetadata": metadata,
                    "modelScored": True,
                    "lastPredictedAt": datetime.now(UTC),
                    "lastPredictionTrigger": trigger_type,
                    "updatedAt": datetime.now(UTC),
                }
            },
        )
