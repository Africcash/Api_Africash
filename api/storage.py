import uuid
from typing import Tuple
from pathlib import Path
from django.conf import settings

# Supported image MIME types
ALLOWED_IMAGE_TYPES = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/webp': '.webp',
    'image/gif': '.gif',
}

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

def upload_object(file_bytes: bytes, original_name: str, content_type: str) -> Tuple[str, str]:
    """
    Saves uploaded file bytes directly to the local media directory (media/uploads/)
    and returns (public_url, object_key).
    """
    ext = ALLOWED_IMAGE_TYPES.get(content_type, Path(original_name).suffix or '.bin')
    object_key = f"{uuid.uuid4().hex}{ext}"

    upload_dir = Path(settings.MEDIA_ROOT) / 'uploads'
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / object_key
    file_path.write_bytes(file_bytes)

    media_url = getattr(settings, 'MEDIA_URL', '/media/').rstrip('/')
    public_url = f"{media_url}/uploads/{object_key}"
    return public_url, object_key
