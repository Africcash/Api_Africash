import os
import uuid
from typing import Tuple, Optional
from pathlib import Path
from django.conf import settings
import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

# Supported image MIME types
ALLOWED_IMAGE_TYPES = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/webp': '.webp',
    'image/gif': '.gif',
}

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

def get_s3_client():
    # Initialize boto3 S3 client for MinIO object storage
    endpoint = getattr(settings, 'MINIO_ENDPOINT', 'http://localhost:9000')
    access_key = getattr(settings, 'MINIO_ACCESS_KEY', 'minioadmin')
    secret_key = getattr(settings, 'MINIO_SECRET_KEY', 'minioadmin')

    return boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1',
    )

def ensure_bucket_exists(s3_client, bucket_name: str):
    # Ensure MinIO bucket exists before uploading
    try:
        s3_client.head_bucket(Bucket=bucket_name)
    except ClientError:
        try:
            s3_client.create_bucket(Bucket=bucket_name)
        except Exception:
            pass

def upload_object(file_bytes: bytes, original_name: str, content_type: str) -> Tuple[str, str]:
    # Uploads object bytes to MinIO storage and returns (public_url, object_key)
    bucket = getattr(settings, 'MINIO_BUCKET_NAME', 'africash-media')
    public_url_base = getattr(settings, 'MINIO_PUBLIC_URL', 'http://localhost:9000').rstrip('/')
    ext = ALLOWED_IMAGE_TYPES.get(content_type, Path(original_name).suffix or '.bin')

    # Generate unique object key
    object_key = f"{uuid.uuid4().hex}{ext}"

    endpoint = getattr(settings, 'MINIO_ENDPOINT', '')
    if endpoint:
        try:
            s3 = get_s3_client()
            ensure_bucket_exists(s3, bucket)
            s3.put_object(
                Bucket=bucket,
                Key=object_key,
                Body=file_bytes,
                ContentType=content_type,
            )
            public_url = f"{public_url_base}/{bucket}/{object_key}"
            return public_url, object_key
        except (BotoCoreError, ClientError, Exception):
            # Fallback to local storage if MinIO is unreachable during local test runs
            pass

    # Local filesystem fallback
    media_dir = Path(settings.BASE_DIR) / 'media' / 'uploads'
    media_dir.mkdir(parents=True, exist_ok=True)
    file_path = media_dir / object_key
    file_path.write_bytes(file_bytes)
    return f"/media/uploads/{object_key}", object_key
