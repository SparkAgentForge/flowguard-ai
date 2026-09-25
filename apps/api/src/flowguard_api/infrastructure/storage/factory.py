"""Select the configured object-storage provider."""

from flowguard_api.config import get_settings
from flowguard_api.core.storage import FileStorage
from flowguard_api.infrastructure.storage.providers import LocalFileStorage, S3FileStorage


def get_file_storage() -> FileStorage:
    settings = get_settings()
    if settings.object_storage_endpoint:
        return S3FileStorage(
            endpoint=settings.object_storage_endpoint,
            public_endpoint=settings.object_storage_public_endpoint,
            bucket=settings.object_storage_bucket,
            access_key=settings.object_storage_access_key,
            secret_key=settings.object_storage_secret_key,
            region=settings.object_storage_region,
        )
    return LocalFileStorage(settings.upload_dir)

