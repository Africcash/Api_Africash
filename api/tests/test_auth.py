import base64
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from stellar_sdk import Keypair

class WalletAuthApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.keypair = Keypair.random()
        self.stellar_address = self.keypair.public_key

    def test_challenge_generation_success(self):
        url = reverse('auth-challenge')
        response = self.client.post(url, {'stellar_address': self.stellar_address}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['stellar_address'], self.stellar_address)
        self.assertIn('nonce', response.data)
        self.assertIn('message', response.data)
        self.assertIn('expires_in', response.data)
        self.assertIn(self.stellar_address, response.data['message'])

    def test_challenge_invalid_stellar_address(self):
        url = reverse('auth-challenge')
        response = self.client.post(url, {'stellar_address': 'INVALID_ADDRESS'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_signature_and_authenticated_me(self):
        # 1. Request challenge
        challenge_url = reverse('auth-challenge')
        challenge_res = self.client.post(challenge_url, {'stellar_address': self.stellar_address}, format='json')
        nonce = challenge_res.data['nonce']
        message = challenge_res.data['message']

        # 2. Sign message
        raw_sig = self.keypair.sign(message.encode('utf-8'))
        sig_b64 = base64.b64encode(raw_sig).decode('utf-8')

        # 3. Verify challenge
        verify_url = reverse('auth-verify')
        verify_res = self.client.post(verify_url, {
            'stellar_address': self.stellar_address,
            'nonce': nonce,
            'signature': sig_b64,
        }, format='json')

        self.assertEqual(verify_res.status_code, status.HTTP_200_OK)
        token = verify_res.data['token']
        self.assertIsNotNone(token)
        self.assertEqual(verify_res.data['stellar_address'], self.stellar_address)
        self.assertFalse(verify_res.data['is_agent'])

        # 4. Use token to access protected endpoint
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        me_url = reverse('auth-me')
        me_res = self.client.get(me_url)
        self.assertEqual(me_res.status_code, status.HTTP_200_OK)
        self.assertEqual(me_res.data['stellar_address'], self.stellar_address)

        # 5. Update user profile display_name and avatar_url
        patch_res = self.client.patch(me_url, {
            'display_name': 'Alice Trader',
            'avatar_url': 'https://images.example.com/avatar1.jpg',
        }, format='json')
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data['display_name'], 'Alice Trader')
        self.assertEqual(patch_res.data['avatar_url'], 'https://images.example.com/avatar1.jpg')

    def test_verify_invalid_signature_rejected(self):
        challenge_url = reverse('auth-challenge')
        challenge_res = self.client.post(challenge_url, {'stellar_address': self.stellar_address}, format='json')
        nonce = challenge_res.data['nonce']

        bad_sig = base64.b64encode(b"0" * 64).decode('utf-8')
        verify_url = reverse('auth-verify')
        verify_res = self.client.post(verify_url, {
            'stellar_address': self.stellar_address,
            'nonce': nonce,
            'signature': bad_sig,
        }, format='json')

        self.assertEqual(verify_res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_replay_attack_prevention(self):
        # Obtain challenge and signature
        challenge_res = self.client.post(reverse('auth-challenge'), {'stellar_address': self.stellar_address}, format='json')
        nonce = challenge_res.data['nonce']
        message = challenge_res.data['message']
        sig_b64 = base64.b64encode(self.keypair.sign(message.encode('utf-8'))).decode('utf-8')

        # First verify succeeds
        verify_res1 = self.client.post(reverse('auth-verify'), {
            'stellar_address': self.stellar_address,
            'nonce': nonce,
            'signature': sig_b64,
        }, format='json')
        self.assertEqual(verify_res1.status_code, status.HTTP_200_OK)

        # Second verify with same nonce MUST fail (nonce destroyed)
        verify_res2 = self.client.post(reverse('auth-verify'), {
            'stellar_address': self.stellar_address,
            'nonce': nonce,
            'signature': sig_b64,
        }, format='json')
        self.assertEqual(verify_res2.status_code, status.HTTP_401_UNAUTHORIZED)
