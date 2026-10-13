from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from stellar_sdk import Keypair

from api.models import AgentProfile
from api.authentication import verify_auth_challenge, generate_auth_challenge

class AgentApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.agent_kp = Keypair.random()
        self.agent_address = self.agent_kp.public_key

        # Create sample agent
        self.agent = AgentProfile.objects.create(
            stellar_address=self.agent_address,
            name="Lagos Marina Exchange",
            phone="+2348012345678",
            address_text="12 Marina Street, Lagos Island",
            city="Lagos",
            country="Nigeria",
            latitude=Decimal('6.454070'),
            longitude=Decimal('3.394670'),
            supported_currencies=["NGN", "GHS"],
            exchange_rates={"NGN": "1550.00", "GHS": "15.80"},
            available_services=["cash_out", "cash_in"],
            fee_percentage=Decimal('1.00'),
            is_available=True,
            reputation_score=Decimal('4.95'),
            completed_trades=42,
            min_usdc_amount=Decimal('5.00'),
            max_usdc_amount=Decimal('1000.00'),
        )

        # Authenticate client as agent
        challenge = generate_auth_challenge(self.agent_address)
        raw_sig = self.agent_kp.sign(challenge['message'].encode('utf-8'))
        import base64
        sig_b64 = base64.b64encode(raw_sig).decode('utf-8')
        self.token = verify_auth_challenge(self.agent_address, challenge['nonce'], sig_b64)

    def test_list_and_filter_agents_public(self):
        url = reverse('agent-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], "Lagos Marina Exchange")

        # Filter by currency
        res_ngn = self.client.get(f"{url}?currency=NGN")
        self.assertEqual(len(res_ngn.data), 1)

        res_kes = self.client.get(f"{url}?currency=KES")
        self.assertEqual(len(res_kes.data), 0)

        # Filter by city
        res_city = self.client.get(f"{url}?city=Lagos")
        self.assertEqual(len(res_city.data), 1)

        res_wrong_city = self.client.get(f"{url}?city=Accra")
        self.assertEqual(len(res_wrong_city.data), 0)

    def test_register_new_agent(self):
        new_user_kp = Keypair.random()
        challenge = generate_auth_challenge(new_user_kp.public_key)
        import base64
        sig = base64.b64encode(new_user_kp.sign(challenge['message'].encode('utf-8'))).decode('utf-8')
        user_token = verify_auth_challenge(new_user_kp.public_key, challenge['nonce'], sig)

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {user_token}')

        payload = {
            "name": "Accra Central POS",
            "phone": "+233201234567",
            "address_text": "High Street, Accra",
            "city": "Accra",
            "country": "Ghana",
            "supported_currencies": ["GHS"],
            "exchange_rates": {"GHS": "15.90"},
            "available_services": ["cash_out"],
            "fee_percentage": "1.50",
            "is_available": True,
            "min_usdc_amount": "10.00",
            "max_usdc_amount": "500.00",
        }

        res = client.post(reverse('agent-list'), payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['stellar_address'], new_user_kp.public_key)
        self.assertEqual(res.data['name'], "Accra Central POS")

    def test_agent_me_endpoint_and_cache_invalidation(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        url = reverse('agent-me')

        # Get own profile
        get_res = self.client.get(url)
        self.assertEqual(get_res.status_code, status.HTTP_200_OK)
        self.assertEqual(get_res.data['name'], "Lagos Marina Exchange")

        # Update availability to False
        patch_res = self.client.patch(url, {'is_available': False}, format='json')
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertFalse(patch_res.data['is_available'])

        # Listing with available=true should now return 0
        list_res = self.client.get(f"{reverse('agent-list')}?available=true")
        self.assertEqual(len(list_res.data), 0)

    def test_agent_search_query(self):
        url = reverse('agent-list')
        # Search by matching name
        res = self.client.get(f"{url}?search=Marina")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)

        # Search by non-matching query
        res_empty = self.client.get(f"{url}?search=NonExistentStore1234")
        self.assertEqual(res_empty.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_empty.data), 0)

    def test_agent_stats_endpoint(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        url = reverse('agent-stats')
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('completed_trades', res.data)
        self.assertIn('active_trades', res.data)
        self.assertIn('total_volume_usdc', res.data)
        self.assertIn('estimated_earnings_usdc', res.data)
        self.assertIn('reputation_score', res.data)
