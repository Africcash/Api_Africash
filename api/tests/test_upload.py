import io
import base64
from unittest.mock import patch, MagicMock
from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient
from stellar_sdk import Keypair
from api.authentication import generate_auth_challenge, verify_auth_challenge
from api.models import UserProfile
from api.storage import upload_object, MAX_FILE_SIZE_BYTES

class FileUploadApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.keypair = Keypair.random()
        self.stellar_address = self.keypair.public_key
        self.user_profile = UserProfile.objects.create(stellar_address=self.stellar_address)

        # Generate auth token
        challenge = generate_auth_challenge(self.stellar_address)
        sig = base64.b64encode(self.keypair.sign(challenge['message'].encode('utf-8'))).decode('utf-8')
        self.token = verify_auth_challenge(self.stellar_address, challenge['nonce'], sig)
        self.upload_url = reverse('file-upload')

    def test_unauthenticated_upload_rejected(self):
        # Unauthenticated users cannot upload files
        dummy_file = SimpleUploadedFile("avatar.jpg", b"dummy image bytes", content_type="image/jpeg")
        response = self.client.post(self.upload_url, {'file': dummy_file}, format='multipart')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_authenticated_upload_missing_file_rejected(self):
        # Missing file field returns 400
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        response = self.client.post(self.upload_url, {}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_authenticated_upload_valid_jpeg(self):
        # Authenticated upload of valid image succeeds
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        img_content = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"
        dummy_file = SimpleUploadedFile("avatar.jpg", img_content, content_type="image/jpeg")

        response = self.client.post(self.upload_url, {'file': dummy_file}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('url', response.data)
        self.assertIn('object_key', response.data)
        self.assertEqual(response.data['content_type'], 'image/jpeg')
        self.assertEqual(response.data['size'], len(img_content))

    def test_authenticated_upload_unsupported_media_type(self):
        # Non-image files like text/plain or executable scripts are rejected
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        dummy_file = SimpleUploadedFile("script.sh", b"#!/bin/bash\necho hack", content_type="text/plain")

        response = self.client.post(self.upload_url, {'file': dummy_file}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertIn("Unsupported media type", response.data['error'])

    def test_authenticated_upload_exceeds_size_limit(self):
        # Files exceeding 5MB are rejected
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        oversized_bytes = b"0" * (MAX_FILE_SIZE_BYTES + 1024)
        dummy_file = SimpleUploadedFile("large_banner.png", oversized_bytes, content_type="image/png")

        response = self.client.post(self.upload_url, {'file': dummy_file}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertIn("File size exceeds 5MB limit", response.data['error'])

    def test_upload_object_saves_to_local_media(self):
        # Test saving uploaded object to local media directory
        data = b"image content test"
        url, key = upload_object(data, "storefront.png", "image/png")

        self.assertTrue(key.endswith('.png'))
        self.assertIn(key, url)
        self.assertTrue(url.startswith('/media/uploads/'))

        # Verify file is written to local filesystem
        file_path = settings.MEDIA_ROOT / 'uploads' / key
        self.assertTrue(file_path.exists())
        self.assertEqual(file_path.read_bytes(), data)
