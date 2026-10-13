import time
from decimal import Decimal
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q, F, Avg
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse

from api.models import AgentProfile, Exchange, ExchangeStatus, AgentReview
from api.storage import upload_object, ALLOWED_IMAGE_TYPES, MAX_FILE_SIZE_BYTES
from api.serializers import (
    AgentProfileSerializer,
    AgentReviewSerializer,
    ExchangeSerializer,
    ExchangeCreateSerializer,
    NotifyFundedSerializer,
    ConfirmCashSerializer,
    NotifyReleasedSerializer,
    CancelExchangeSerializer,
    DisputeExchangeSerializer,
    ReviewCreateSerializer,
    ConfigSerializer,
    FileUploadRequestSerializer,
    FileUploadResponseSerializer,
)

CACHE_KEY_AGENTS_PREFIX = "africash_agents_list"
CACHE_TTL_AGENTS = 60  # 1 minute

def invalidate_agents_cache():
    # Invalidate all cached agent search queries
    cache.delete_many([
        f"{CACHE_KEY_AGENTS_PREFIX}_all",
        f"{CACHE_KEY_AGENTS_PREFIX}_available",
    ])

class AgentViewSet(viewsets.ModelViewSet):
    serializer_class = AgentProfileSerializer
    queryset = AgentProfile.objects.all().order_by('-reputation_score', '-completed_trades')

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'reviews']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    @extend_schema(
        summary="List and discover available cash agents",
        description="Returns cash agent profiles with optional filtering by search query, supported fiat currency, city, availability, and verification status. Cached for high performance.",
        parameters=[
            OpenApiParameter("search", str, description="Search by agent name, city, or street address"),
            OpenApiParameter("currency", str, description="Filter by supported fiat currency (e.g. NGN, GHS, KES)"),
            OpenApiParameter("city", str, description="Filter by city name"),
            OpenApiParameter("available", bool, description="Filter by online availability (true/false)"),
            OpenApiParameter("verified", bool, description="Filter by verification badge (true/false)"),
        ],
        tags=["Cash Agents"]
    )
    def list(self, request, *args, **kwargs):
        currency = request.query_params.get('currency', '').strip().upper()
        city = request.query_params.get('city', '').strip()
        search = (request.query_params.get('search') or request.query_params.get('q') or '').strip()
        available_param = request.query_params.get('available')
        verified_param = request.query_params.get('verified')

        cache_key = f"{CACHE_KEY_AGENTS_PREFIX}_{currency}_{city}_{available_param}_{verified_param}_{search}"
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data)

        queryset = self.filter_queryset(self.get_queryset())

        if currency:
            queryset = queryset.filter(supported_currencies__icontains=currency)
        if city:
            queryset = queryset.filter(city__icontains=city)
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(city__icontains=search) |
                Q(address_text__icontains=search)
            )
        if available_param is not None:
            is_avail = available_param.lower() in ['true', '1']
            queryset = queryset.filter(is_available=is_avail)
        if verified_param is not None:
            is_ver = verified_param.lower() in ['true', '1']
            queryset = queryset.filter(is_verified=is_ver)

        serializer = self.get_serializer(queryset, many=True)
        data = serializer.data
        cache.set(cache_key, data, timeout=CACHE_TTL_AGENTS)
        return Response(data)

    @extend_schema(
        summary="Register as a cash agent",
        description="Creates a new cash agent profile bound to the authenticated Stellar wallet address.",
        tags=["Cash Agents"]
    )
    def create(self, request, *args, **kwargs):
        stellar_address = getattr(request.user, 'stellar_address', request.user.username)
        if AgentProfile.objects.filter(stellar_address=stellar_address).exists():
            return Response(
                {"error": "An agent profile already exists for this wallet address."},
                status=status.HTTP_400_BAD_REQUEST
            )

        data = request.data.copy()
        data['stellar_address'] = stellar_address

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        invalidate_agents_cache()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Get or update own agent profile",
        description="Retrieve or modify availability, fees, operating hours, or rates for the currently authenticated agent.",
        tags=["Cash Agents"]
    )
    @action(detail=False, methods=['get', 'patch', 'put'], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        stellar_address = getattr(request.user, 'stellar_address', request.user.username)
        try:
            agent = AgentProfile.objects.get(stellar_address=stellar_address)
        except AgentProfile.DoesNotExist:
            return Response(
                {"error": "No agent profile found for this wallet."},
                status=status.HTTP_404_NOT_FOUND
            )

        if request.method == 'GET':
            serializer = self.get_serializer(agent)
            return Response(serializer.data)

        serializer = self.get_serializer(agent, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        invalidate_agents_cache()
        return Response(serializer.data)

    @extend_schema(
        summary="Get agent dashboard statistics",
        description="Returns trading statistics for the currently authenticated agent (completed trades, total volume, active trades, earnings).",
        tags=["Cash Agents"]
    )
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def stats(self, request):
        stellar_address = getattr(request.user, 'stellar_address', request.user.username)
        try:
            agent = AgentProfile.objects.get(stellar_address=stellar_address)
        except AgentProfile.DoesNotExist:
            return Response({"error": "No agent profile found for this wallet."}, status=status.HTTP_404_NOT_FOUND)

        completed_exchanges = Exchange.objects.filter(agent=agent, status=ExchangeStatus.RELEASED)
        active_exchanges = Exchange.objects.filter(
            agent=agent,
            status__in=[ExchangeStatus.INITIATED, ExchangeStatus.FUNDED, ExchangeStatus.CASH_PENDING, ExchangeStatus.CASH_CONFIRMED]
        )

        total_volume_usdc = sum((e.usdc_amount for e in completed_exchanges), Decimal('0.00'))
        total_earnings_usdc = sum((e.usdc_amount * (agent.fee_percentage / Decimal('100')) for e in completed_exchanges), Decimal('0.00')).quantize(Decimal('0.01'))

        return Response({
            "completed_trades": completed_exchanges.count(),
            "active_trades": active_exchanges.count(),
            "total_volume_usdc": str(total_volume_usdc),
            "estimated_earnings_usdc": str(total_earnings_usdc),
            "reputation_score": str(agent.reputation_score),
            "review_count": agent.reviews.count(),
            "is_available": agent.is_available,
        })

    @extend_schema(
        summary="List customer reviews for an agent",
        description="Returns ratings and testimonials left by traders who completed cash-out exchanges with this agent.",
        responses={200: AgentReviewSerializer(many=True)},
        tags=["Cash Agents"]
    )
    @action(detail=True, methods=['get'])
    def reviews(self, request, pk=None):
        agent = self.get_object()
        reviews = agent.reviews.all().order_by('-created_at')
        return Response(AgentReviewSerializer(reviews, many=True).data)

    def perform_update(self, serializer):
        serializer.save()
        invalidate_agents_cache()

    def perform_destroy(self, instance):
        instance.delete()
        invalidate_agents_cache()

class ExchangeViewSet(viewsets.ModelViewSet):
    serializer_class = ExchangeSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        # Users only see exchanges they are party to
        stellar_address = getattr(self.request.user, 'stellar_address', self.request.user.username)
        queryset = Exchange.objects.filter(
            Q(user_address=stellar_address) | Q(agent__stellar_address=stellar_address)
        ).select_related('agent', 'review').order_by('-created_at')

        role = self.request.query_params.get('role', '').lower()
        if role == 'user':
            queryset = queryset.filter(user_address=stellar_address)
        elif role == 'agent':
            queryset = queryset.filter(agent__stellar_address=stellar_address)

        status_param = self.request.query_params.get('status')
        if status_param:
            status_param = status_param.strip().upper()
            if status_param == 'ACTIVE':
                queryset = queryset.filter(
                    status__in=[ExchangeStatus.INITIATED, ExchangeStatus.FUNDED, ExchangeStatus.CASH_PENDING, ExchangeStatus.CASH_CONFIRMED]
                )
            elif status_param == 'COMPLETED':
                queryset = queryset.filter(status=ExchangeStatus.RELEASED)
            elif status_param == 'CANCELLED':
                queryset = queryset.filter(status__in=[ExchangeStatus.CANCELLED, ExchangeStatus.REFUNDED])
            else:
                queryset = queryset.filter(status=status_param)

        return queryset

    @extend_schema(
        summary="Initiate a USDC cash-out exchange",
        description="Initiates an exchange with a chosen cash agent. Server computes accurate fiat payout, generates a secure 6-digit OTP and SHA-256 secret hash for the Soroban escrow contract.",
        request=ExchangeCreateSerializer,
        responses={201: ExchangeSerializer},
        tags=["Exchanges & Escrow"]
    )
    def create(self, request, *args, **kwargs):
        serializer = ExchangeCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        exchange = serializer.save()

        # Bind configured testnet contract addresses
        exchange.escrow_contract_id = getattr(settings, 'ESCROW_CONTRACT_ID', '')
        exchange.token_address = getattr(settings, 'USDC_ASSET_CONTRACT_ID', '')
        exchange.save(update_fields=['escrow_contract_id', 'token_address'])

        response_serializer = ExchangeSerializer(exchange)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Notify that USDC funds are locked in escrow",
        description="Called after user signs on-chain transaction calling lock_funds on the Soroban escrow contract. Updates status from INITIATED to FUNDED.",
        request=NotifyFundedSerializer,
        responses={200: ExchangeSerializer},
        tags=["Exchanges & Escrow"]
    )
    @action(detail=True, methods=['post'], url_path='notify-funded')
    def notify_funded(self, request, pk=None):
        exchange = self.get_object()
        user_address = getattr(request.user, 'stellar_address', request.user.username)

        if exchange.user_address != user_address:
            return Response(
                {"error": "Only the initiating user can record escrow funding."},
                status=status.HTTP_403_FORBIDDEN
            )

        if exchange.status != ExchangeStatus.INITIATED:
            return Response(
                {"error": f"Cannot fund exchange in status {exchange.status}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = NotifyFundedSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        exchange.lock_tx_hash = serializer.validated_data['tx_hash']
        contract_id = serializer.validated_data.get('contract_id')
        if contract_id:
            exchange.escrow_contract_id = contract_id
        exchange.status = ExchangeStatus.FUNDED
        exchange.save()

        return Response(ExchangeSerializer(exchange).data)

    @extend_schema(
        summary="Confirm physical cash handover",
        description="Confirms that physical cash was delivered. Can be confirmed by user directly or by agent supplying the user's OTP secret. Updates status to CASH_CONFIRMED.",
        request=ConfirmCashSerializer,
        responses={200: ExchangeSerializer},
        tags=["Exchanges & Escrow"]
    )
    @action(detail=True, methods=['post'], url_path='confirm-cash')
    def confirm_cash(self, request, pk=None):
        exchange = self.get_object()
        stellar_address = getattr(request.user, 'stellar_address', request.user.username)

        if exchange.status != ExchangeStatus.FUNDED:
            return Response(
                {"error": f"Cannot confirm cash for exchange in status {exchange.status}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = ConfirmCashSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        secret = serializer.validated_data.get('secret', '').strip()

        is_user = (exchange.user_address == stellar_address)
        is_agent = (exchange.agent.stellar_address == stellar_address)

        if is_agent:
            # Agent must provide valid secret OTP to prove handover
            if not secret or secret != exchange.secret:
                return Response(
                    {"error": "Invalid handover secret / OTP."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        elif not is_user:
            return Response({"error": "Unauthorized."}, status=status.HTTP_403_FORBIDDEN)

        exchange.status = ExchangeStatus.CASH_CONFIRMED
        exchange.save(update_fields=['status', 'updated_at'])

        return Response(ExchangeSerializer(exchange).data)

    @extend_schema(
        summary="Notify that USDC funds are released to agent",
        description="Records the on-chain release transaction hash after release_by_user or release_with_secret is confirmed. Updates status to RELEASED and increments agent trade count.",
        request=NotifyReleasedSerializer,
        responses={200: ExchangeSerializer},
        tags=["Exchanges & Escrow"]
    )
    @action(detail=True, methods=['post'], url_path='notify-released')
    def notify_released(self, request, pk=None):
        exchange = self.get_object()

        if exchange.status not in [ExchangeStatus.FUNDED, ExchangeStatus.CASH_CONFIRMED]:
            return Response(
                {"error": f"Cannot release exchange in status {exchange.status}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = NotifyReleasedSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        exchange.release_tx_hash = serializer.validated_data['tx_hash']
        exchange.status = ExchangeStatus.RELEASED
        exchange.save()

        # Increment agent's completed trades counter
        AgentProfile.objects.filter(id=exchange.agent_id).update(
            completed_trades=F('completed_trades') + 1
        )
        invalidate_agents_cache()

        return Response(ExchangeSerializer(exchange).data)

    @extend_schema(
        summary="Cancel or refund an exchange",
        description="Allows agent to cancel before payout or user to refund if timeout has elapsed. Records transaction hash if refund occurred on-chain.",
        request=CancelExchangeSerializer,
        responses={200: ExchangeSerializer},
        tags=["Exchanges & Escrow"]
    )
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        exchange = self.get_object()
        stellar_address = getattr(request.user, 'stellar_address', request.user.username)

        if exchange.status in [ExchangeStatus.RELEASED, ExchangeStatus.REFUNDED, ExchangeStatus.CANCELLED]:
            return Response(
                {"error": f"Exchange is already resolved with status {exchange.status}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = CancelExchangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tx_hash = serializer.validated_data.get('tx_hash')
        reason = serializer.validated_data.get('reason', '').strip()

        is_user = (exchange.user_address == stellar_address)
        is_agent = (exchange.agent.stellar_address == stellar_address)

        if not (is_user or is_agent):
            return Response({"error": "Unauthorized."}, status=status.HTTP_403_FORBIDDEN)

        now = int(time.time())
        if is_user and exchange.status == ExchangeStatus.FUNDED and now < exchange.timeout_timestamp:
            return Response(
                {"error": f"Escrow timeout not yet reached. Refund allowed after {exchange.timeout_timestamp}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if reason:
            exchange.cancellation_reason = reason

        if exchange.status == ExchangeStatus.FUNDED:
            exchange.status = ExchangeStatus.REFUNDED
            if tx_hash:
                exchange.refund_tx_hash = tx_hash
        else:
            exchange.status = ExchangeStatus.CANCELLED

        exchange.save()
        return Response(ExchangeSerializer(exchange).data)

    @extend_schema(
        summary="Report a dispute on an exchange",
        description="Allows either party to flag an issue during physical cash handover, transitioning status to DISPUTED.",
        request=DisputeExchangeSerializer,
        responses={200: ExchangeSerializer},
        tags=["Exchanges & Escrow"]
    )
    @action(detail=True, methods=['post'])
    def dispute(self, request, pk=None):
        exchange = self.get_object()
        stellar_address = getattr(request.user, 'stellar_address', request.user.username)

        if exchange.user_address != stellar_address and exchange.agent.stellar_address != stellar_address:
            return Response({"error": "Unauthorized."}, status=status.HTTP_403_FORBIDDEN)

        if exchange.status not in [ExchangeStatus.FUNDED, ExchangeStatus.CASH_PENDING]:
            return Response(
                {"error": f"Cannot dispute exchange in status {exchange.status}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = DisputeExchangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        exchange.status = ExchangeStatus.DISPUTED
        exchange.notes = f"Dispute: {serializer.validated_data['reason']}"
        exchange.save(update_fields=['status', 'notes', 'updated_at'])

        return Response(ExchangeSerializer(exchange).data)

    @extend_schema(
        summary="Leave a rating and review for an agent",
        description="Allows the customer to submit a 1 to 5 star rating and comment after funds are released. Automatically recalculates agent reputation score.",
        request=ReviewCreateSerializer,
        responses={201: AgentReviewSerializer},
        tags=["Exchanges & Escrow"]
    )
    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        exchange = self.get_object()
        stellar_address = getattr(request.user, 'stellar_address', request.user.username)

        if exchange.user_address != stellar_address:
            return Response({"error": "Only the customer can review the agent."}, status=status.HTTP_403_FORBIDDEN)

        if exchange.status != ExchangeStatus.RELEASED:
            return Response({"error": "Can only review completed (RELEASED) exchanges."}, status=status.HTTP_400_BAD_REQUEST)

        if hasattr(exchange, 'review'):
            return Response({"error": "A review has already been submitted for this exchange."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        rev = AgentReview.objects.create(
            exchange=exchange,
            agent=exchange.agent,
            user_address=stellar_address,
            rating=serializer.validated_data['rating'],
            comment=serializer.validated_data.get('comment', ''),
        )

        # Recalculate average reputation score
        avg_rating = exchange.agent.reviews.aggregate(Avg('rating'))['rating__avg']
        if avg_rating is not None:
            exchange.agent.reputation_score = Decimal(str(round(avg_rating, 2)))
            exchange.agent.save(update_fields=['reputation_score'])
            invalidate_agents_cache()

        return Response(AgentReviewSerializer(rev).data, status=status.HTTP_201_CREATED)

class ConfigView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="Retrieve Stellar Testnet network and contract configuration",
        description="Returns Stellar network passphrase, RPC URL, Horizon URL, USDC Asset Contract ID, and Escrow Contract ID for frontend integration.",
        responses={200: ConfigSerializer},
        tags=["System Configuration"]
    )
    def get(self, request):
        data = {
            "network_passphrase": getattr(settings, 'STELLAR_NETWORK_PASSPHRASE', 'Test SDF Network ; September 2015'),
            "rpc_url": getattr(settings, 'STELLAR_RPC_URL', 'https://soroban-testnet.stellar.org'),
            "horizon_url": getattr(settings, 'STELLAR_HORIZON_URL', 'https://horizon-testnet.stellar.org'),
            "usdc_contract_id": getattr(settings, 'USDC_ASSET_CONTRACT_ID', ''),
            "escrow_contract_id": getattr(settings, 'ESCROW_CONTRACT_ID', ''),
        }
        return Response(data)

class FileUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        summary="Upload image to MinIO object storage",
        description="Upload an avatar image or agent storefront picture to MinIO S3 object storage (max 5MB, JPG/PNG/WEBP/GIF). Returns the public CDN / storage URL.",
        request=FileUploadRequestSerializer,
        responses={201: FileUploadResponseSerializer, 400: OpenApiResponse(description="Invalid file or size exceeded")},
        tags=["Object Storage"]
    )
    def post(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({"error": "No file uploaded. Please supply 'file' field."}, status=status.HTTP_400_BAD_REQUEST)

        if file_obj.size > MAX_FILE_SIZE_BYTES:
            return Response({"error": f"File size exceeds 5MB limit ({file_obj.size} bytes)."}, status=status.HTTP_400_BAD_REQUEST)

        content_type = file_obj.content_type
        if content_type not in ALLOWED_IMAGE_TYPES:
            return Response({
                "error": f"Unsupported media type '{content_type}'. Allowed types: {', '.join(ALLOWED_IMAGE_TYPES.keys())}"
            }, status=status.HTTP_400_BAD_REQUEST)

        file_bytes = file_obj.read()
        public_url, object_key = upload_object(file_bytes, file_obj.name, content_type)

        return Response({
            "url": public_url,
            "object_key": object_key,
            "content_type": content_type,
            "size": len(file_bytes),
        }, status=status.HTTP_201_CREATED)
