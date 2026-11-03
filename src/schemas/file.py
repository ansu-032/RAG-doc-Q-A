import datetime
import uuid

from pydantic import BaseModel, ConfigDict


class FileOut(BaseModel):
    """Everything stored about a file in the uploaded_files table."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    mime_type: str
    file_extension: str | None
    size_bytes: int
    sha256_checksum: str
    minio_bucket: str
    minio_object_key: str
    minio_etag: str | None
    page_count: int | None
    chunk_count: int
    status: str
    error_message: str | None
    uploaded_at: datetime.datetime
    processed_at: datetime.datetime | None
    updated_at: datetime.datetime
