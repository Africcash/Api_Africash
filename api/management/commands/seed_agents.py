from decimal import Decimal
from django.core.management.base import BaseCommand
from api.models import AgentProfile, UserProfile
from api.views import invalidate_agents_cache


DEFAULT_AGENTS = [
    {
        "stellar_address": "GBF4JEUCD6NEQZZO4WGHUOQXDFZ7HRZWVNGDONJ2ZMCDCOAYEFNJU27E",
        "name": "Lagos Marina POS Hub",
        "avatar_url": "https://api.dicebear.com/7.x/identicon/svg?seed=LagosMarina",
        "phone": "+2348012345678",
        "email": "marina@africash.io",
        "address_text": "12 Marina Street, Lagos Island",
        "city": "Lagos",
        "country": "Nigeria",
        "latitude": Decimal("6.454070"),
        "longitude": Decimal("3.394670"),
        "supported_currencies": ["NGN", "GHS"],
        "exchange_rates": {"NGN": "1580.00", "GHS": "15.85"},
        "available_services": ["cash_out", "cash_in", "bank_transfer"],
        "handover_methods": ["physical_cash", "pos_counter", "bank_transfer"],
        "operating_hours": "08:00 - 20:00",
        "fee_percentage": Decimal("1.00"),
        "is_available": True,
        "is_verified": True,
        "reputation_score": Decimal("4.95"),
        "completed_trades": 142,
        "min_usdc_amount": Decimal("5.00"),
        "max_usdc_amount": Decimal("2500.00"),
    },
    {
        "stellar_address": "GAB7TJERCOPRG7P5LZ7T63WUQ46HFLT2CFOH2ZKONV32MXD66KQXERUC",
        "name": "Victoria Island Express Cash",
        "avatar_url": "https://api.dicebear.com/7.x/identicon/svg?seed=VictoriaIsland",
        "phone": "+2348098765432",
        "email": "vi.express@africash.io",
        "address_text": "24 Adeola Odeku Street, Victoria Island",
        "city": "Lagos",
        "country": "Nigeria",
        "latitude": Decimal("6.428055"),
        "longitude": Decimal("3.421994"),
        "supported_currencies": ["NGN"],
        "exchange_rates": {"NGN": "1590.00"},
        "available_services": ["cash_out", "cash_in"],
        "handover_methods": ["physical_cash", "pos_counter"],
        "operating_hours": "07:30 - 21:00",
        "fee_percentage": Decimal("0.85"),
        "is_available": True,
        "is_verified": True,
        "reputation_score": Decimal("4.98"),
        "completed_trades": 218,
        "min_usdc_amount": Decimal("10.00"),
        "max_usdc_amount": Decimal("5000.00"),
    },
    {
        "stellar_address": "GDFOTL7DUXRDB5UUWVNC4GVFINHSO3M63DMU7LGLWGMASYOYTJNMBRAO",
        "name": "Wuse II Central Bureau & POS",
        "avatar_url": "https://api.dicebear.com/7.x/identicon/svg?seed=AbujaWuse",
        "phone": "+2348033445566",
        "email": "wuse@africash.io",
        "address_text": "45 Aminu Kano Crescent, Wuse II",
        "city": "Abuja",
        "country": "Nigeria",
        "latitude": Decimal("9.076479"),
        "longitude": Decimal("7.476309"),
        "supported_currencies": ["NGN"],
        "exchange_rates": {"NGN": "1575.00"},
        "available_services": ["cash_out", "cash_in", "bank_transfer"],
        "handover_methods": ["physical_cash", "pos_counter"],
        "operating_hours": "08:00 - 19:00",
        "fee_percentage": Decimal("1.10"),
        "is_available": True,
        "is_verified": True,
        "reputation_score": Decimal("4.89"),
        "completed_trades": 96,
        "min_usdc_amount": Decimal("5.00"),
        "max_usdc_amount": Decimal("2000.00"),
    },
    {
        "stellar_address": "GAJVKLC6PZQNFH7TTPSJCMS22DENJLGXJIE64U4K42N3IXOJ6ANPLWAK",
        "name": "Accra Osu Oxford Street POS",
        "avatar_url": "https://api.dicebear.com/7.x/identicon/svg?seed=AccraOsu",
        "phone": "+233241234567",
        "email": "osu@africash.io",
        "address_text": "18 Cantonments Road, Osu",
        "city": "Accra",
        "country": "Ghana",
        "latitude": Decimal("5.556020"),
        "longitude": Decimal("-0.182420"),
        "supported_currencies": ["GHS", "NGN"],
        "exchange_rates": {"GHS": "15.90", "NGN": "1565.00"},
        "available_services": ["cash_out", "cash_in", "mobile_money"],
        "handover_methods": ["physical_cash", "mobile_money", "pos_counter"],
        "operating_hours": "08:00 - 20:30",
        "fee_percentage": Decimal("1.20"),
        "is_available": True,
        "is_verified": True,
        "reputation_score": Decimal("4.92"),
        "completed_trades": 175,
        "min_usdc_amount": Decimal("5.00"),
        "max_usdc_amount": Decimal("1500.00"),
    },
    {
        "stellar_address": "GATVSBGUNP7VM2PNKMNQ66DY637Q73JMFZJBV4QS2QYX755GP4NFT5L4",
        "name": "Kumasi Adum Mobile & Cash Point",
        "avatar_url": "https://api.dicebear.com/7.x/identicon/svg?seed=KumasiAdum",
        "phone": "+233207654321",
        "email": "kumasi@africash.io",
        "address_text": "Prempeh II Street, Adum",
        "city": "Kumasi",
        "country": "Ghana",
        "latitude": Decimal("6.688480"),
        "longitude": Decimal("-1.624430"),
        "supported_currencies": ["GHS"],
        "exchange_rates": {"GHS": "15.80"},
        "available_services": ["cash_out", "mobile_money"],
        "handover_methods": ["physical_cash", "mobile_money"],
        "operating_hours": "08:30 - 18:30",
        "fee_percentage": Decimal("1.25"),
        "is_available": True,
        "is_verified": False,
        "reputation_score": Decimal("4.80"),
        "completed_trades": 54,
        "min_usdc_amount": Decimal("5.00"),
        "max_usdc_amount": Decimal("800.00"),
    },
    {
        "stellar_address": "GB6EHW4XWKVYNZHUZHPSGOCDHMWSXXSDJGKZV4YXBCSYYOG3U2UINTZV",
        "name": "Nairobi Westlands M-Pesa & Cash",
        "avatar_url": "https://api.dicebear.com/7.x/identicon/svg?seed=NairobiWestlands",
        "phone": "+254712345678",
        "email": "westlands@africash.io",
        "address_text": "Mpaka Road, Westlands",
        "city": "Nairobi",
        "country": "Kenya",
        "latitude": Decimal("-1.264790"),
        "longitude": Decimal("36.802790"),
        "supported_currencies": ["KES", "UGX"],
        "exchange_rates": {"KES": "129.50", "UGX": "3710.00"},
        "available_services": ["cash_out", "cash_in", "mobile_money"],
        "handover_methods": ["physical_cash", "mobile_money", "pos_counter"],
        "operating_hours": "07:00 - 21:00",
        "fee_percentage": Decimal("0.90"),
        "is_available": True,
        "is_verified": True,
        "reputation_score": Decimal("4.97"),
        "completed_trades": 310,
        "min_usdc_amount": Decimal("5.00"),
        "max_usdc_amount": Decimal("3000.00"),
    },
    {
        "stellar_address": "GA63P37KQM4A6OCKXYWINHPSBDV6VUZLRQEP3IPDDKAJ5OCO24JSGPGR",
        "name": "Nairobi CBD Kenyatta Ave Kiosk",
        "avatar_url": "https://api.dicebear.com/7.x/identicon/svg?seed=NairobiCBD",
        "phone": "+254722987654",
        "email": "cbd.nairobi@africash.io",
        "address_text": "Kenyatta Avenue, CBD",
        "city": "Nairobi",
        "country": "Kenya",
        "latitude": Decimal("-1.284100"),
        "longitude": Decimal("36.823500"),
        "supported_currencies": ["KES"],
        "exchange_rates": {"KES": "129.00"},
        "available_services": ["cash_out", "cash_in"],
        "handover_methods": ["physical_cash", "pos_counter"],
        "operating_hours": "08:00 - 19:30",
        "fee_percentage": Decimal("1.00"),
        "is_available": True,
        "is_verified": True,
        "reputation_score": Decimal("4.86"),
        "completed_trades": 128,
        "min_usdc_amount": Decimal("5.00"),
        "max_usdc_amount": Decimal("1500.00"),
    },
    {
        "stellar_address": "GCICUZEDA7A6HLADKM2IRMMREGQ7ODFHYZ6G2AUSU36HFN4HLZKGS62R",
        "name": "Kampala Road Express Forex & POS",
        "avatar_url": "https://api.dicebear.com/7.x/identicon/svg?seed=KampalaRoad",
        "phone": "+256772123456",
        "email": "kampala@africash.io",
        "address_text": "32 Kampala Road, Central Division",
        "city": "Kampala",
        "country": "Uganda",
        "latitude": Decimal("0.313611"),
        "longitude": Decimal("32.581111"),
        "supported_currencies": ["UGX", "KES"],
        "exchange_rates": {"UGX": "3725.00", "KES": "128.80"},
        "available_services": ["cash_out", "cash_in", "mobile_money"],
        "handover_methods": ["physical_cash", "mobile_money"],
        "operating_hours": "08:00 - 20:00",
        "fee_percentage": Decimal("1.15"),
        "is_available": True,
        "is_verified": True,
        "reputation_score": Decimal("4.91"),
        "completed_trades": 87,
        "min_usdc_amount": Decimal("5.00"),
        "max_usdc_amount": Decimal("1200.00"),
    },
    {
        "stellar_address": "GCVHE2V63VIZTLY2QBY2JEW5ENRQYSD2XQMFDX5RQO7HGCKXWTJXP4WH",
        "name": "Kigali Heights Cash & MoMo Desk",
        "avatar_url": "https://api.dicebear.com/7.x/identicon/svg?seed=KigaliHeights",
        "phone": "+250788123456",
        "email": "kigali@africash.io",
        "address_text": "KG 7 Ave, Kimihurura",
        "city": "Kigali",
        "country": "Rwanda",
        "latitude": Decimal("-1.953590"),
        "longitude": Decimal("30.092780"),
        "supported_currencies": ["RWF", "KES"],
        "exchange_rates": {"RWF": "1360.00", "KES": "128.50"},
        "available_services": ["cash_out", "cash_in", "mobile_money"],
        "handover_methods": ["physical_cash", "mobile_money", "pos_counter"],
        "operating_hours": "08:00 - 20:00",
        "fee_percentage": Decimal("1.00"),
        "is_available": True,
        "is_verified": True,
        "reputation_score": Decimal("4.94"),
        "completed_trades": 112,
        "min_usdc_amount": Decimal("5.00"),
        "max_usdc_amount": Decimal("2000.00"),
    },
    {
        "stellar_address": "GDRKWF22XCQI375QUL3GRBKBEU6DVLFOLUUXCOYE6JSSSVVSU7276J6U",
        "name": "Dakar Plateau Point Cash XOF",
        "avatar_url": "https://api.dicebear.com/7.x/identicon/svg?seed=DakarPlateau",
        "phone": "+221771234567",
        "email": "dakar@africash.io",
        "address_text": "Avenue Léopold Sédar Senghor, Plateau",
        "city": "Dakar",
        "country": "Senegal",
        "latitude": Decimal("14.669260"),
        "longitude": Decimal("-17.438100"),
        "supported_currencies": ["XOF"],
        "exchange_rates": {"XOF": "605.00"},
        "available_services": ["cash_out", "cash_in", "mobile_money"],
        "handover_methods": ["physical_cash", "mobile_money"],
        "operating_hours": "08:30 - 19:30",
        "fee_percentage": Decimal("1.20"),
        "is_available": True,
        "is_verified": True,
        "reputation_score": Decimal("4.88"),
        "completed_trades": 74,
        "min_usdc_amount": Decimal("10.00"),
        "max_usdc_amount": Decimal("1500.00"),
    },
]


class Command(BaseCommand):
    help = "Seed the database with initial cash agent profiles upon deployment (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite existing seeded agent profiles with default values.",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)
        created_count = 0
        updated_count = 0
        skipped_count = 0

        for agent_data in DEFAULT_AGENTS:
            stellar_address = agent_data["stellar_address"]
            defaults = {k: v for k, v in agent_data.items() if k != "stellar_address"}

            if force:
                _, created = AgentProfile.objects.update_or_create(
                    stellar_address=stellar_address,
                    defaults=defaults,
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1
            else:
                _, created = AgentProfile.objects.get_or_create(
                    stellar_address=stellar_address,
                    defaults=defaults,
                )
                if created:
                    created_count += 1
                else:
                    skipped_count += 1

            UserProfile.objects.get_or_create(
                stellar_address=stellar_address,
                defaults={
                    "display_name": agent_data["name"],
                    "avatar_url": agent_data.get("avatar_url", ""),
                },
            )

        invalidate_agents_cache()

        self.stdout.write(
            self.style.SUCCESS(
                f"Agent seeding complete: {created_count} created, "
                f"{updated_count} updated, {skipped_count} already existed "
                f"(total in DB: {AgentProfile.objects.count()})."
            )
        )
