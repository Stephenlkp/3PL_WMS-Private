import re
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.domain.enums import Role
from app.models.entities import StoredFile, User
from app.services.audit import write_audit

ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "application/pdf": ".pdf",
}

_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def sniff_type(data: bytes, declared: str | None) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        found = "image/jpeg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        found = "image/png"
    elif data.startswith(b"%PDF"):
        found = "application/pdf"
    else:
        raise AppError("Only JPEG, PNG, and PDF files are accepted", 400, "unsupported_file")
    if declared:
        normalized = declared.split(";")[0].strip().lower()
        if normalized == "image/jpg":
            normalized = "image/jpeg"
        if normalized in ALLOWED_TYPES and normalized != found:
            raise AppError("File contents do not match its type", 400, "file_type_mismatch")
    return found


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise AppError("File missing from storage", 404, "missing_file")
        return path.read_bytes()

    def _path(self, key: str) -> Path:
        parts = Path(key).parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise AppError("Invalid storage key", 400, "invalid_key")
        return self.root.joinpath(*parts)


class MinioStorage:
    def __init__(self):
        from minio import Minio

        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        if not self.client.bucket_exists(settings.MINIO_BUCKET):
            self.client.make_bucket(settings.MINIO_BUCKET)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        import io

        self.client.put_object(
            settings.MINIO_BUCKET,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )

    def get(self, key: str) -> bytes:
        response = self.client.get_object(settings.MINIO_BUCKET, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()


def get_storage():
    if settings.STORAGE_BACKEND == "minio":
        return MinioStorage()
    return LocalStorage(settings.LOCAL_STORAGE_PATH)


def store_bytes(
    session: Session,
    user: User,
    *,
    filename: str,
    declared_type: str | None,
    data: bytes,
    customer_id: uuid.UUID | None,
    ip: str | None,
) -> StoredFile:
    if len(data) == 0:
        raise AppError("File is empty", 400, "empty_file")
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise AppError("File is larger than 10 MB", 413, "file_too_large")
    content_type = sniff_type(data, declared_type)
    safe_name = _FILENAME.sub("-", Path(filename or "upload").name).strip("-") or "upload"
    suffix = ALLOWED_TYPES[content_type]
    if not safe_name.lower().endswith(suffix) and not (suffix == ".jpg" and safe_name.lower().endswith(".jpeg")):
        safe_name = f"{safe_name}{suffix}"
    key = f"{customer_id or 'warehouse'}/{uuid.uuid4().hex}/{safe_name}"
    bucket = settings.MINIO_BUCKET if settings.STORAGE_BACKEND == "minio" else "local"
    get_storage().put(key, data, content_type)
    stored = StoredFile(
        customer_id=customer_id,
        bucket=bucket,
        object_key=key,
        filename=safe_name,
        content_type=content_type,
        size_bytes=len(data),
        uploaded_by=user.id,
    )
    session.add(stored)
    session.flush()
    write_audit(
        session,
        user=user,
        action="file.upload",
        entity_type="file",
        entity_id=stored.id,
        ip=ip,
        customer_id=customer_id,
        new={"filename": safe_name, "content_type": content_type, "size_bytes": len(data)},
    )
    return stored


def read_file(session: Session, user: User, file_id: uuid.UUID) -> tuple[StoredFile, bytes]:
    stored = session.get(StoredFile, file_id)
    if stored is None:
        raise AppError("File not found", 404, "not_found")
    if stored.customer_id is not None and user.role == Role.CUSTOMER and user.customer_id != stored.customer_id:
        raise AppError("File not found", 404, "not_found")
    return stored, get_storage().get(stored.object_key)
