from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse
from api.authentication import generate_auth_challenge, verify_auth_challenge
from api.models import AgentProfile, UserProfile
from api.serializers import (
    WalletChallengeRequestSerializer,
    WalletChallengeResponseSerializer,
    WalletVerifyRequestSerializer,
    WalletVerifyResponseSerializer,
    WalletMeResponseSerializer,
    WalletMeUpdateSerializer,
)

class WalletChallengeView(APIView):
    # Rate limit challenge requests to mitigate spam
    throttle_scope = 'auth_challenge'
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="Request a cryptographic authentication challenge",
        description="Generates an Ed25519 challenge nonce for a connected Stellar wallet. The frontend should prompt the user's wallet (e.g. via Stellar Wallets Kit) to sign this message.",
        request=WalletChallengeRequestSerializer,
        responses={
            200: WalletChallengeResponseSerializer,
            400: OpenApiResponse(description="Invalid Stellar address"),
        },
        tags=["Wallet Authentication"]
    )
    def post(self, request):
        serializer = WalletChallengeRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        stellar_address = serializer.validated_data['stellar_address']
        challenge_data = generate_auth_challenge(stellar_address)
        return Response(challenge_data, status=status.HTTP_200_OK)

class WalletVerifyView(APIView):
    # Rate limit verification attempts
    throttle_scope = 'auth_challenge'
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="Verify signed wallet challenge and obtain session token",
        description="Verifies the Ed25519 signature produced by the wallet over the challenge message. Returns a session bearer token along with user profile data.",
        request=WalletVerifyRequestSerializer,
        responses={
            200: WalletVerifyResponseSerializer,
            400: OpenApiResponse(description="Invalid request or signature"),
            401: OpenApiResponse(description="Signature verification failed or challenge expired"),
        },
        tags=["Wallet Authentication"]
    )
    def post(self, request):
        serializer = WalletVerifyRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        stellar_address = serializer.validated_data['stellar_address']
        nonce = serializer.validated_data['nonce']
        signature = serializer.validated_data['signature']

        token = verify_auth_challenge(stellar_address, nonce, signature)
        if not token:
            return Response(
                {"error": "Invalid signature or expired challenge nonce."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Get or create persistent UserProfile
        user_profile, _ = UserProfile.objects.get_or_create(stellar_address=stellar_address)
        is_agent = AgentProfile.objects.filter(stellar_address=stellar_address).exists()

        return Response({
            "token": token,
            "stellar_address": stellar_address,
            "display_name": user_profile.display_name,
            "avatar_url": user_profile.avatar_url,
            "is_agent": is_agent,
        }, status=status.HTTP_200_OK)

class WalletMeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Get authenticated wallet profile",
        description="Returns details for the currently authenticated wallet address, including display name, avatar, and agent registration status.",
        responses={
            200: WalletMeResponseSerializer,
            401: OpenApiResponse(description="Unauthenticated"),
        },
        tags=["Wallet Authentication"]
    )
    def get(self, request):
        stellar_address = getattr(request.user, 'stellar_address', request.user.username)
        user_profile, _ = UserProfile.objects.get_or_create(stellar_address=stellar_address)
        agent_qs = AgentProfile.objects.filter(stellar_address=stellar_address)
        is_agent = agent_qs.exists()
        agent_id = agent_qs.first().id if is_agent else None

        return Response({
            "stellar_address": stellar_address,
            "display_name": user_profile.display_name,
            "avatar_url": user_profile.avatar_url,
            "is_agent": is_agent,
            "agent_id": agent_id,
        })

    @extend_schema(
        summary="Update authenticated user profile",
        description="Update display name or avatar URL for the connected wallet.",
        request=WalletMeUpdateSerializer,
        responses={
            200: WalletMeResponseSerializer,
            400: OpenApiResponse(description="Validation error"),
        },
        tags=["Wallet Authentication"]
    )
    def patch(self, request):
        stellar_address = getattr(request.user, 'stellar_address', request.user.username)
        user_profile, _ = UserProfile.objects.get_or_create(stellar_address=stellar_address)

        serializer = WalletMeUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        if 'display_name' in serializer.validated_data:
            user_profile.display_name = serializer.validated_data['display_name']
        if 'avatar_url' in serializer.validated_data:
            user_profile.avatar_url = serializer.validated_data['avatar_url']

        user_profile.save()

        agent_qs = AgentProfile.objects.filter(stellar_address=stellar_address)
        is_agent = agent_qs.exists()
        agent_id = agent_qs.first().id if is_agent else None

        return Response({
            "stellar_address": stellar_address,
            "display_name": user_profile.display_name,
            "avatar_url": user_profile.avatar_url,
            "is_agent": is_agent,
            "agent_id": agent_id,
        })
