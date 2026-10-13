from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

class DocumentationEndpointsTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_openapi_schema_endpoint(self):
        url = reverse('schema')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('openapi', response.content.decode('utf-8'))

    def test_swagger_ui_endpoint(self):
        url = reverse('swagger-ui')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(b'swagger-ui', response.content)

    def test_redoc_endpoint(self):
        url = reverse('redoc')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(b'redoc', response.content)
