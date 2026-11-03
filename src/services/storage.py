import io

from minio import Minio

from src.config import settings

# The minio client is synchronous: call these with asyncio.to_thread from async code.
client = Minio(
    settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=False,
)


def ensure_bucket() -> None:
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)


def put_file(key: str, data: bytes, content_type: str) -> str:
    result = client.put_object(
        settings.minio_bucket, key, io.BytesIO(data), len(data), content_type=content_type
    )
    return result.etag


def get_file(key: str) -> bytes:
    response = client.get_object(settings.minio_bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def delete_file(key: str) -> None:
    client.remove_object(settings.minio_bucket, key)
