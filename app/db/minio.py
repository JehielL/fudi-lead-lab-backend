from minio import Minio

from app.core.config import Settings


def get_minio_client(settings: Settings) -> Minio:
    return Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key.get_secret_value(),
        secure=settings.minio_secure,
    )


def close_minio_client(_client: Minio) -> None:
    return None

