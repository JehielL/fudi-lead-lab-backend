from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import Settings


def get_mongo_client(settings: Settings) -> AsyncIOMotorClient:
    return AsyncIOMotorClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=int(settings.dependency_check_timeout_seconds * 1000),
    )


def get_mongo_database(client: AsyncIOMotorClient, settings: Settings):
    return client[settings.mongodb_database]


def close_mongo_client(client: AsyncIOMotorClient) -> None:
    client.close()

