from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle
from stellar_sdk import Keypair

class ThrottlingTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.keypair = Keypair.random()
        self.original_rates = ScopedRateThrottle.THROTTLE_RATES
        ScopedRateThrottle.THROTTLE_RATES = {
            'auth_challenge': '3/minute',
            'anon': '100/minute',
            'user': '1000/minute',
        }

    def tearDown(self):
        ScopedRateThrottle.THROTTLE_RATES = self.original_rates
        cache.clear()

    def test_challenge_endpoint_throttled(self):
        url = reverse('auth-challenge')
        # Send 3 requests (within limit)
        for _ in range(3):
            res = self.client.post(url, {'stellar_address': self.keypair.public_key}, format='json')
            self.assertEqual(res.status_code, status.HTTP_200_OK)

        # 4th request within the same minute should be throttled
        res_throttled = self.client.post(url, {'stellar_address': self.keypair.public_key}, format='json')
        self.assertEqual(res_throttled.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
