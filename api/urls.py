from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api.auth_views import WalletChallengeView, WalletVerifyView, WalletMeView
from api.views import AgentViewSet, ExchangeViewSet, ConfigView, FileUploadView

router = DefaultRouter()
router.register(r'agents', AgentViewSet, basename='agent')
router.register(r'exchanges', ExchangeViewSet, basename='exchange')

urlpatterns = [
    # Non-custodial wallet authentication
    path('auth/challenge/', WalletChallengeView.as_view(), name='auth-challenge'),
    path('auth/verify/', WalletVerifyView.as_view(), name='auth-verify'),
    path('auth/me/', WalletMeView.as_view(), name='auth-me'),

    # MinIO Object storage
    path('upload/', FileUploadView.as_view(), name='file-upload'),

    # Network configuration
    path('config/', ConfigView.as_view(), name='system-config'),

    # Agents and Escrow exchanges
    path('', include(router.urls)),
]
