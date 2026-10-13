"""Object storage. Domain services depend on this protocol, not SDK clients."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, urlsplit
from uuid import UUID

import httpx

from app.core.config import get_settings


class ObjectStorageProvider(Protocol):
    def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def presign(self, key: str, *, expires_seconds: int = 300) -> str: ...


class LocalObjectStorageProvider:
    def __init__(self, root: str | None = None) -> None:
        settings = get_settings()
        self.root = Path(root or settings.object_storage_local_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str:
        _ = content_type
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def exists(self, key: str) -> bool:
        return (self.root / key).exists()

    def presign(self, key: str, *, expires_seconds: int = 300) -> str:
        _ = expires_seconds
        return f"/api/v1/ai/knowledge/files/{quote(key, safe='')}"


class S3CompatibleObjectStorageProvider:
    """Path-style S3/MinIO via boto3 when configured, otherwise HTTP PUT to the endpoint."""

    def __init__(self) -> None:
        settings = get_settings()
        self.endpoint = settings.s3_endpoint.rstrip("/")
        self.bucket = settings.s3_bucket
        self.access_key = settings.s3_access_key
        self.secret_key = settings.s3_secret_key

    def _client(self):
        import boto3
        from botocore.client import Config

        return boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )

    def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str:
        try:
            self._client().put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
            return key
        except Exception:
            response = self._put_http(key, data, content_type=content_type)
            if response.status_code == 404 and b"NoSuchBucket" in response.content:
                self._create_bucket()
                response = self._put_http(key, data, content_type=content_type)
            response.raise_for_status()
            return key

    def _put_http(self, key: str, data: bytes, *, content_type: str) -> httpx.Response:
        url, headers = self._signed("PUT", key, data, content_type=content_type)
        return httpx.put(url, content=data, headers=headers, timeout=15.0)

    def _create_bucket(self) -> None:
        url, headers = self._signed_uri("PUT", "/" + quote(self.bucket, safe=""), b"")
        httpx.put(url, content=b"", headers=headers, timeout=15.0).raise_for_status()

    def get(self, key: str) -> bytes:
        try:
            return self._client().get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except Exception:
            url, headers = self._signed("GET", key, b"")
            response = httpx.get(url, headers=headers, timeout=15.0)
            response.raise_for_status()
            return response.content

    def exists(self, key: str) -> bool:
        try:
            self._client().head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            try:
                url, headers = self._signed("HEAD", key, b"")
                httpx.head(url, headers=headers, timeout=15.0).raise_for_status()
                return True
            except Exception:
                return False

    def _signed(self, method: str, key: str, data: bytes, *, content_type: str | None = None) -> tuple[str, dict[str, str]]:
        canonical_uri = "/" + quote(self.bucket, safe="") + "/" + quote(key, safe="/")
        return self._signed_uri(method, canonical_uri, data, content_type=content_type)

    def _signed_uri(
        self, method: str, canonical_uri: str, data: bytes, *, content_type: str | None = None
    ) -> tuple[str, dict[str, str]]:
        now = datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        datestamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(data).hexdigest()
        parts = urlsplit(self.endpoint)
        header_map = {
            "host": parts.netloc,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        if content_type:
            header_map["content-type"] = content_type
        names = sorted(header_map)
        canonical_headers = "".join(f"{name}:{header_map[name]}\n" for name in names)
        signed_headers = ";".join(names)
        canonical_request = "\n".join(
            [method, canonical_uri, "", canonical_headers, signed_headers, payload_hash]
        )
        scope = f"{datestamp}/us-east-1/s3/aws4_request"
        string_to_sign = "\n".join(
            ["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical_request.encode()).hexdigest()]
        )
        signature = hmac.new(_aws_signing_key(self.secret_key, datestamp), string_to_sign.encode(), hashlib.sha256).hexdigest()
        header_map["Authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return f"{parts.scheme}://{parts.netloc}{canonical_uri}", header_map

    def presign(self, key: str, *, expires_seconds: int = 300) -> str:
        try:
            return self._client().generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_seconds,
            )
        except Exception:
            return f"/api/v1/ai/knowledge/files/{quote(key, safe='')}"


class MinioObjectStorageProvider(S3CompatibleObjectStorageProvider):
    pass


class S3ObjectStorageProvider(S3CompatibleObjectStorageProvider):
    pass


def knowledge_object_key(*, tenant_id: UUID, document_id: UUID, version: str = "v1") -> str:
    return f"tenant/{tenant_id}/knowledge/{document_id}/{version}/source"


def model_artifact_key(*, tenant_id: UUID, task_key: str, version: str) -> str:
    return f"tenant/{tenant_id}/models/{task_key}/{version}/artifact"


def dataset_object_key(*, tenant_id: UUID, task_key: str, version: str) -> str:
    return f"tenant/{tenant_id}/models/{task_key}/{version}/dataset.jsonl"


def get_object_storage() -> ObjectStorageProvider:
    settings = get_settings()
    backend = (settings.object_storage_provider or "local").lower()
    if backend in {"minio", "s3"} and settings.s3_endpoint:
        if backend == "minio":
            return MinioObjectStorageProvider()
        return S3ObjectStorageProvider()
    return LocalObjectStorageProvider()


def content_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _aws_signing_key(secret: str, datestamp: str) -> bytes:
    date_key = hmac.new(f"AWS4{secret}".encode(), datestamp.encode(), hashlib.sha256).digest()
    region_key = hmac.new(date_key, b"us-east-1", hashlib.sha256).digest()
    service_key = hmac.new(region_key, b"s3", hashlib.sha256).digest()
    return hmac.new(service_key, b"aws4_request", hashlib.sha256).digest()
