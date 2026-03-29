"""Storage backends for item image uploads."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, Protocol

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


ALLOWED_UPLOAD_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_UPLOAD_EXTENSIONS


def _join_public_url(base: str, path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    if not base:
        return normalized_path
    return f"{base.rstrip('/')}{normalized_path}"


class StorageBackend(Protocol):
    """Common interface for upload storage providers."""

    kind: str

    def upload(self, file: FileStorage, *, public_base_url: str = "") -> Dict[str, Any]:
        """Upload an image and return standardized metadata."""


class LocalStorageBackend:
    """Store files on local filesystem and serve through Flask static route."""

    kind = "local"

    def __init__(self) -> None:
        upload_folder = os.getenv(
            "UPLOAD_FOLDER",
            str(Path(__file__).resolve().parent / "uploads"),
        )
        self.upload_dir = Path(upload_folder)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def upload(self, file: FileStorage, *, public_base_url: str = "") -> Dict[str, Any]:
        filename = secure_filename(file.filename or "")
        if not filename:
            raise ValueError("filename is required")
        if not _allowed_file(filename):
            raise ValueError("unsupported file type")

        extension = filename.rsplit(".", 1)[1].lower()
        generated = f"{uuid.uuid4().hex}.{extension}"
        target = self.upload_dir / generated
        file.save(target)

        relative_url = f"/uploads/{generated}"
        absolute_url = _join_public_url(public_base_url, relative_url)
        return {
            "image_filename": generated,
            "image_url": absolute_url,
            "image_meta": {"provider": self.kind, "path": str(target)},
        }


class CloudinaryStorageBackend:
    """Store files on Cloudinary and return secure URL."""

    kind = "cloudinary"

    def __init__(self) -> None:
        cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
        api_key = os.getenv("CLOUDINARY_API_KEY", "").strip()
        api_secret = os.getenv("CLOUDINARY_API_SECRET", "").strip()
        if not all([cloud_name, api_key, api_secret]):
            raise ValueError("Cloudinary selected but credentials are missing")

        try:
            import cloudinary
            import cloudinary.uploader
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("Cloudinary SDK is not installed") from exc

        self._uploader = cloudinary.uploader
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True,
        )
        self.folder = os.getenv("CLOUDINARY_FOLDER", "lost_and_found").strip() or "lost_and_found"

    def upload(self, file: FileStorage, *, public_base_url: str = "") -> Dict[str, Any]:
        _ = public_base_url
        filename = secure_filename(file.filename or "")
        if not filename:
            raise ValueError("filename is required")
        if not _allowed_file(filename):
            raise ValueError("unsupported file type")

        resource = self._uploader.upload(
            file.stream,
            resource_type="image",
            folder=self.folder,
            overwrite=False,
            unique_filename=True,
        )
        secure_url = str(resource.get("secure_url", "")).strip()
        public_id = str(resource.get("public_id", "")).strip()
        if not secure_url:
            raise RuntimeError("Cloudinary upload did not return a URL")
        return {
            "image_filename": public_id,
            "image_url": secure_url,
            "image_meta": {"provider": self.kind, "public_id": public_id},
        }


class S3StorageBackend:
    """Store files on Amazon S3 and return public URL."""

    kind = "s3"

    def __init__(self) -> None:
        self.bucket = os.getenv("S3_BUCKET_NAME", "").strip()
        self.region = os.getenv("AWS_REGION", "").strip()
        access_key = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
        if not all([self.bucket, self.region, access_key, secret_key]):
            raise ValueError("S3 selected but AWS credentials/bucket are missing")
        try:
            import boto3
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("boto3 is not installed") from exc
        session = boto3.session.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=self.region,
        )
        self.client = session.client("s3")
        self.prefix = os.getenv("S3_KEY_PREFIX", "lost-and-found").strip("/") or "lost-and-found"

    def upload(self, file: FileStorage, *, public_base_url: str = "") -> Dict[str, Any]:
        _ = public_base_url
        filename = secure_filename(file.filename or "")
        if not filename:
            raise ValueError("filename is required")
        if not _allowed_file(filename):
            raise ValueError("unsupported file type")

        extension = filename.rsplit(".", 1)[1].lower()
        key = f"{self.prefix}/{uuid.uuid4().hex}.{extension}"
        content_type = file.mimetype or f"image/{extension}"
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=file.stream.read(),
            ContentType=content_type,
            ACL="public-read",
        )
        public_url = f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{key}"
        return {
            "image_filename": key,
            "image_url": public_url,
            "image_meta": {"provider": self.kind, "bucket": self.bucket, "key": key},
        }


def build_storage_backend() -> StorageBackend:
    """Build storage backend from STORAGE_PROVIDER environment."""
    provider = os.getenv("STORAGE_PROVIDER", "local").strip().lower()
    if provider == "cloudinary":
        return CloudinaryStorageBackend()
    if provider == "s3":
        return S3StorageBackend()
    return LocalStorageBackend()
