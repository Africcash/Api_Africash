import base64
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from stellar_sdk import Keypair

from api.models import AgentProfile, ExchangeStatus
from api.authentication import verify_auth_challenge, generate_auth_challenge

class ExchangeApiTest(TestCase):
    def setUp(self):
        # Setup agent
        self.agent_kp = Keypair.random()
        self.agent_address = self.agent_kp.public_key
        self.agent = AgentProfile.objects.create(
            stellar_address=self.agent_address,
            name="FastCash Victoria Island",
            phone="+2348099887766",
            address_text="Plot 5, Adeola Odeku, VI, Lagos",
            city="Lagos",
            country="Nigeria",
            supported_currencies=["NGN"],
            exchange_rates={"NGN": "1500.00"},
            available_services=["cash_out"],
            fee_percentage=Decimal('1.00'),
            is_available=True,
            min_usdc_amount=Decimal('10.00'),
            max_usdc_amount=Decimal('500.00'),
        )

        # Setup customer
        self.user_kp = Keypair.random()
        self.user_address = self.user_kp.public_key

        # Customer token
        ch_user = generate_auth_challenge(self.user_address)
        sig_user = base64.b64encode(self.user_kp.sign(ch_user['message'].encode('utf-8'))).decode('utf-8')
        self.user_token = verify_auth_challenge(self.user_address, ch_user['nonce'], sig_user)
        self.user_client = APIClient()
        self.user_client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.user_token}')

        # Agent token
        ch_agent = generate_auth_challenge(self.agent_address)
        sig_agent = base64.b64encode(self.agent_kp.sign(ch_agent['message'].encode('utf-8'))).decode('utf-8')
        self.agent_token = verify_auth_challenge(self.agent_address, ch_agent['nonce'], sig_agent)
        self.agent_client = APIClient()
        self.agent_client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.agent_token}')

    def test_complete_exchange_lifecycle(self):
        # 1. Customer initiates exchange for 50.00 USDC
        init_res = self.user_client.post(reverse('exchange-list'), {
            "agent_id": self.agent.id,
            "usdc_amount": "50.00",
            "fiat_currency": "NGN",
            "notes": "Meet at VI branch",
        }, format='json')

        self.assertEqual(init_res.status_code, status.HTTP_201_CREATED)
        exchange_id_pk = init_res.data['id']
        onchain_exchange_id = init_res.data['exchange_id']
        secret_otp = init_res.data['secret']
        self.assertEqual(init_res.data['status'], ExchangeStatus.INITIATED)
        self.assertEqual(Decimal(init_res.data['fiat_amount']), Decimal('75000.00'))  # 50 * 1500
        self.assertTrue(len(secret_otp) == 6)

        # 2. Customer locks funds in Soroban escrow and notifies backend
        funded_url = reverse('exchange-notify-funded', args=[exchange_id_pk])
        funded_res = self.user_client.post(funded_url, {
            "tx_hash": "a1b2c3d4e5f60718293a4b5c6d7e8f901234567890abcdef1234567890abcdef",
        }, format='json')

        self.assertEqual(funded_res.status_code, status.HTTP_200_OK)
        self.assertEqual(funded_res.data['status'], ExchangeStatus.FUNDED)

        # 3. Agent confirms cash handover using customer's secret OTP
        confirm_url = reverse('exchange-confirm-cash', args=[exchange_id_pk])
        # Wrong secret fails
        bad_confirm = self.agent_client.post(confirm_url, {"secret": "000000"}, format='json')
        self.assertEqual(bad_confirm.status_code, status.HTTP_400_BAD_REQUEST)

        # Correct secret succeeds
        confirm_res = self.agent_client.post(confirm_url, {"secret": secret_otp}, format='json')
        self.assertEqual(confirm_res.status_code, status.HTTP_200_OK)
        self.assertEqual(confirm_res.data['status'], ExchangeStatus.CASH_CONFIRMED)

        # 4. User/Contract releases funds to agent
        initial_trades = AgentProfile.objects.get(id=self.agent.id).completed_trades
        release_url = reverse('exchange-notify-released', args=[exchange_id_pk])
        release_res = self.user_client.post(release_url, {
            "tx_hash": "release_tx_hash_123456789012345678901234567890",
        }, format='json')

        self.assertEqual(release_res.status_code, status.HTTP_200_OK)
        self.assertEqual(release_res.data['status'], ExchangeStatus.RELEASED)

        # Agent's completed_trades count should be incremented
        updated_agent = AgentProfile.objects.get(id=self.agent.id)
        self.assertEqual(updated_agent.completed_trades, initial_trades + 1)

    def test_amount_limits_validation(self):
        # Below min amount (10.00 USDC)
        low_res = self.user_client.post(reverse('exchange-list'), {
            "agent_id": self.agent.id,
            "usdc_amount": "2.00",
            "fiat_currency": "NGN",
        }, format='json')
        self.assertEqual(low_res.status_code, status.HTTP_400_BAD_REQUEST)

        # Above max amount (500.00 USDC)
        high_res = self.user_client.post(reverse('exchange-list'), {
            "agent_id": self.agent.id,
            "usdc_amount": "1000.00",
            "fiat_currency": "NGN",
        }, format='json')
        self.assertEqual(high_res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_agent_cancel_exchange(self):
        # Initiate exchange
        init_res = self.user_client.post(reverse('exchange-list'), {
            "agent_id": self.agent.id,
            "usdc_amount": "20.00",
            "fiat_currency": "NGN",
        }, format='json')
        exchange_id = init_res.data['id']

        # Agent cancels before funding
        cancel_url = reverse('exchange-cancel', args=[exchange_id])
        cancel_res = self.agent_client.post(cancel_url, {"reason": "Out of cash"}, format='json')
        self.assertEqual(cancel_res.status_code, status.HTTP_200_OK)
        self.assertEqual(cancel_res.data['status'], ExchangeStatus.CANCELLED)

    def test_review_agent_and_reputation_update(self):
        # 1. Complete exchange
        init_res = self.user_client.post(reverse('exchange-list'), {
            "agent_id": self.agent.id,
            "usdc_amount": "50.00",
            "fiat_currency": "NGN",
        }, format='json')
        exchange_id = init_res.data['id']
        self.user_client.post(reverse('exchange-notify-funded', args=[exchange_id]), {"tx_hash": "tx_mock_1234567890"}, format='json')
        self.user_client.post(reverse('exchange-notify-released', args=[exchange_id]), {"tx_hash": "tx_mock_release_1234567890"}, format='json')

        # 2. User submits review
        review_url = reverse('exchange-review', args=[exchange_id])
        rev_res = self.user_client.post(review_url, {
            "rating": 5,
            "comment": "Excellent service and instant cash payout!",
        }, format='json')
        self.assertEqual(rev_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(rev_res.data['rating'], 5)

        # 3. Agent reviews list
        agent_reviews_url = reverse('agent-reviews', args=[self.agent.id])
        reviews_res = self.user_client.get(agent_reviews_url)
        self.assertEqual(reviews_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(reviews_res.data), 1)

    def test_dispute_exchange(self):
        init_res = self.user_client.post(reverse('exchange-list'), {
            "agent_id": self.agent.id,
            "usdc_amount": "30.00",
            "fiat_currency": "NGN",
        }, format='json')
        exchange_id = init_res.data['id']
        self.user_client.post(reverse('exchange-notify-funded', args=[exchange_id]), {"tx_hash": "tx_mock_1234567890"}, format='json')

        dispute_url = reverse('exchange-dispute', args=[exchange_id])
        dispute_res = self.user_client.post(dispute_url, {
            "reason": "Agent did not show up at agreed location",
        }, format='json')
        self.assertEqual(dispute_res.status_code, status.HTTP_200_OK)
        self.assertEqual(dispute_res.data['status'], ExchangeStatus.DISPUTED)

    def test_system_config_endpoint(self):
        client = APIClient()
        res = client.get(reverse('system-config'))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('network_passphrase', res.data)
        self.assertIn('rpc_url', res.data)
        self.assertIn('horizon_url', res.data)
        self.assertIn('usdc_contract_id', res.data)
        self.assertIn('escrow_contract_id', res.data)

    def test_exchange_filtering_by_status_and_role(self):
        # Create exchange
        init_res = self.user_client.post(reverse('exchange-list'), {
            "agent_id": self.agent.id,
            "usdc_amount": "25.00",
            "fiat_currency": "NGN",
        }, format='json')
        self.assertEqual(init_res.status_code, status.HTTP_201_CREATED)
        self.assertIn('agent_avatar_url', init_res.data)
        self.assertIn('user_display_name', init_res.data)

        # Filter by active status
        res_active = self.user_client.get(f"{reverse('exchange-list')}?status=ACTIVE")
        self.assertEqual(res_active.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_active.data), 1)

        # Filter by completed status (should be empty initially)
        res_completed = self.user_client.get(f"{reverse('exchange-list')}?status=COMPLETED")
        self.assertEqual(res_completed.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_completed.data), 0)

        # Filter by role
        res_user_role = self.user_client.get(f"{reverse('exchange-list')}?role=user")
        self.assertEqual(len(res_user_role.data), 1)
        res_agent_role = self.user_client.get(f"{reverse('exchange-list')}?role=agent")
        self.assertEqual(len(res_agent_role.data), 0)
