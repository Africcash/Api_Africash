from decimal import Decimal
from django.db import models

class UserProfile(models.Model):
    # Non-custodial user profile bound to connected Stellar wallet
    stellar_address = models.CharField(max_length=56, unique=True, db_index=True)
    display_name = models.CharField(max_length=100, blank=True)
    avatar_url = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.display_name or self.stellar_address[:6]}...{self.stellar_address[-4:]}"

class AgentProfile(models.Model):
    # Stellar public address of the cash agent
    stellar_address = models.CharField(max_length=56, unique=True, db_index=True)
    name = models.CharField(max_length=150)
    avatar_url = models.CharField(max_length=500, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    address_text = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    supported_currencies = models.JSONField(default=list)
    exchange_rates = models.JSONField(default=dict)
    available_services = models.JSONField(default=list)
    handover_methods = models.JSONField(default=list)
    operating_hours = models.CharField(max_length=100, blank=True, default="08:00 - 20:00")
    fee_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('1.00'))
    is_available = models.BooleanField(default=True, db_index=True)
    is_verified = models.BooleanField(default=False, db_index=True)
    reputation_score = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal('5.00'))
    completed_trades = models.PositiveIntegerField(default=0)
    min_usdc_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('5.00'))
    max_usdc_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('1000.00'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.stellar_address[:6]}...{self.stellar_address[-4:]})"

class ExchangeStatus(models.TextChoices):
    INITIATED = 'INITIATED', 'Initiated'
    FUNDED = 'FUNDED', 'Funded (Escrow Locked)'
    CASH_PENDING = 'CASH_PENDING', 'Cash Pending'
    CASH_CONFIRMED = 'CASH_CONFIRMED', 'Cash Confirmed'
    RELEASED = 'RELEASED', 'Released'
    CANCELLED = 'CANCELLED', 'Cancelled'
    REFUNDED = 'REFUNDED', 'Refunded'
    DISPUTED = 'DISPUTED', 'Disputed'

class Exchange(models.Model):
    # Matches Soroban escrow contract exchange_id
    exchange_id = models.BigIntegerField(unique=True, db_index=True)
    user_address = models.CharField(max_length=56, db_index=True)
    agent = models.ForeignKey(AgentProfile, on_delete=models.CASCADE, related_name='exchanges')
    usdc_amount = models.DecimalField(max_digits=18, decimal_places=6)
    fiat_currency = models.CharField(max_length=10)
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=4)
    fiat_amount = models.DecimalField(max_digits=18, decimal_places=2)
    secret_hash = models.CharField(max_length=64, blank=True)
    secret = models.CharField(max_length=64, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ExchangeStatus.choices,
        default=ExchangeStatus.INITIATED,
        db_index=True
    )
    escrow_contract_id = models.CharField(max_length=64, blank=True)
    token_address = models.CharField(max_length=64, blank=True)
    lock_tx_hash = models.CharField(max_length=66, blank=True, null=True)
    release_tx_hash = models.CharField(max_length=66, blank=True, null=True)
    refund_tx_hash = models.CharField(max_length=66, blank=True, null=True)
    timeout_timestamp = models.BigIntegerField()
    cancellation_reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Exchange #{self.exchange_id} - {self.status} ({self.usdc_amount} USDC)"

class AgentReview(models.Model):
    exchange = models.OneToOneField(Exchange, on_delete=models.CASCADE, related_name='review')
    agent = models.ForeignKey(AgentProfile, on_delete=models.CASCADE, related_name='reviews')
    user_address = models.CharField(max_length=56)
    rating = models.PositiveSmallIntegerField(default=5)  # 1 to 5 stars
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review for {self.agent.name}: {self.rating} stars by {self.user_address[:6]}..."
