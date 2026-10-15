import os
import time
import secrets
from typing import Optional, Tuple
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from api.security import validate_stellar_address, verify_stellar_signature

User = get_user_model()

DEFAULT_CHALLENGE_TIMEOUT_SECONDS = 900  # 15 minutes

def get_challenge_timeout_seconds() -> int:
    try:
        val = getattr(settings, 'CHALLENGE_TIMEOUT_SECONDS', None)
        if val is not None:
            return int(val)
    except Exception:
        pass
    return int(os.getenv('CHALLENGE_TIMEOUT_SECONDS', DEFAULT_CHALLENGE_TIMEOUT_SECONDS))

CHALLENGE_TIMEOUT_SECONDS = get_challenge_timeout_seconds()
SESSION_TIMEOUT_SECONDS = 86400 * 7  # 7 days

def generate_auth_challenge(stellar_address: str) -> dict:
    # Generate cryptographic challenge for wallet signing
    if not validate_stellar_address(stellar_address):
        raise ValueError("Invalid Stellar public key format")

    nonce = secrets.token_hex(16)
    timestamp = int(time.time())
    message = (
        f"AfriCash Authentication\n"
        f"Address: {stellar_address}\n"
        f"Nonce: {nonce}\n"
        f"Timestamp: {timestamp}"
    )

    timeout = get_challenge_timeout_seconds()
    cache_key = f"auth_challenge_{stellar_address}_{nonce}"
    cache.set(cache_key, message, timeout=timeout)

    return {
        "stellar_address": stellar_address,
        "nonce": nonce,
        "timestamp": timestamp,
        "message": message,
        "expires_in": timeout,
    }

def verify_auth_challenge(stellar_address: str, nonce: str, signature: str) -> Optional[str]:
    # Verify wallet signature and generate session token
    cache_key = f"auth_challenge_{stellar_address}_{nonce}"
    expected_message = cache.get(cache_key)

    if not expected_message:
        return None

    # Enforce single-use nonce
    cache.delete(cache_key)

    if not verify_stellar_signature(stellar_address, expected_message, signature):
        return None

    # Generate persistent session token
    token = secrets.token_hex(32)
    token_key = f"wallet_auth_{token}"
    cache.set(token_key, stellar_address, timeout=SESSION_TIMEOUT_SECONDS)

    # Ensure Django User exists for compatibility
    user, _ = User.objects.get_or_create(
        username=stellar_address,
        defaults={"is_active": True}
    )

    return token

class StellarWalletAuthentication(authentication.BaseAuthentication):
    # Authenticate requests using Bearer token or direct wallet headers
    def authenticate_header(self, request) -> str:
        return 'Bearer realm="api"'

    def authenticate(self, request) -> Optional[Tuple[User, str]]:
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() not in ("bearer", "token"):
            return None

        token = parts[1]
        token_key = f"wallet_auth_{token}"
        stellar_address = cache.get(token_key)

        if not stellar_address:
            raise exceptions.AuthenticationFailed("Invalid or expired session token")

        try:
            user, _ = User.objects.get_or_create(
                username=stellar_address,
                defaults={"is_active": True}
            )
            # Attach wallet address directly to user instance
            user.stellar_address = stellar_address
            return (user, token)
        except Exception as e:
            raise exceptions.AuthenticationFailed(f"User authentication error: {str(e)}")

class StellarWalletAuthScheme(OpenApiAuthenticationExtension):
    # OpenAPI security definition for StellarWalletAuthentication
    target_class = 'api.authentication.StellarWalletAuthentication'
    name = 'StellarWalletAuth'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'Token',
            'description': 'Stellar wallet session token obtained from /api/auth/verify/. Accepts "Bearer <token>" or "Token <token>".',
        }
