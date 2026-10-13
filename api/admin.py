from django.contrib import admin
from api.models import AgentProfile, Exchange, UserProfile, AgentReview

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('stellar_address', 'display_name', 'created_at')
    search_fields = ('stellar_address', 'display_name')

@admin.register(AgentProfile)
class AgentProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'stellar_address', 'city', 'country', 'is_available', 'is_verified', 'reputation_score', 'completed_trades')
    list_filter = ('is_available', 'is_verified', 'country', 'city')
    search_fields = ('name', 'stellar_address', 'city')

@admin.register(Exchange)
class ExchangeAdmin(admin.ModelAdmin):
    list_display = ('exchange_id', 'user_address', 'agent', 'usdc_amount', 'fiat_currency', 'fiat_amount', 'status', 'created_at')
    list_filter = ('status', 'fiat_currency')
    search_fields = ('exchange_id', 'user_address', 'lock_tx_hash', 'release_tx_hash')

@admin.register(AgentReview)
class AgentReviewAdmin(admin.ModelAdmin):
    list_display = ('agent', 'user_address', 'rating', 'created_at')
    list_filter = ('rating',)
    search_fields = ('agent__name', 'user_address', 'comment')
