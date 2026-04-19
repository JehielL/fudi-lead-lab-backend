from typing import Annotated

from fastapi import Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import Settings, get_settings


def get_database(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIOMotorDatabase:
    return request.app.state.mongo_client[settings.mongodb_database]
