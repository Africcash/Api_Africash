import re
import base64
from decimal import Decimal
from typing import Optional
from stellar_sdk import StrKey, Keypair
from stellar_sdk.exceptions import BadSignatureError

# Pre-compiled HTML tag regex for sanitization
TAG_RE = re.compile(r'<[^>]+>')

def validate_stellar_address(address: str) -> bool:
    # Validate format of Stellar Ed25519 public address (G...)
    if not address or not isinstance(address, str):
        return False
    if len(address) != 56 or not address.startswith('G'):
        return False
    try:
        return StrKey.is_valid_ed25519_public_key(address)
    except Exception:
        return False

def verify_stellar_signature(public_key: str, message: str, signature_data: str) -> bool:
    # Verify Ed25519 signature over message bytes using public key
    if not validate_stellar_address(public_key):
        return False
    if not message or not signature_data:
        return False

    # Decode signature bytes from base64 or hex
    sig_bytes = None
    try:
        sig_bytes = base64.b64decode(signature_data)
        if len(sig_bytes) != 64:
            sig_bytes = None
    except Exception:
        pass

    if sig_bytes is None:
        try:
            sig_bytes = bytes.fromhex(signature_data)
            if len(sig_bytes) != 64:
                return False
        except Exception:
            return False

    try:
        verifier = Keypair.from_public_key(public_key)
        candidates = [message]
        if '\r\n' in message:
            candidates.append(message.replace('\r\n', '\n'))
        elif '\n' in message:
            candidates.append(message.replace('\n', '\r\n'))

        for candidate in candidates:
            # 1. Standard SEP-53 message verification (Freighter, Hana, LOBSTR, xBull)
            try:
                verifier.verify_message(candidate, sig_bytes)
                return True
            except BadSignatureError:
                pass
            except Exception:
                pass

            # 2. Raw signature fallback (scripts, direct Keypair.sign)
            try:
                verifier.verify(candidate.encode('utf-8'), sig_bytes)
                return True
            except BadSignatureError:
                pass
            except Exception:
                pass

        return False
    except (BadSignatureError, Exception):
        return False

def sanitize_text(text: Optional[str], max_length: int = 500) -> str:
    # Strip HTML tags and control characters to prevent XSS and injection
    if not text:
        return ""
    cleaned = TAG_RE.sub('', str(text))
    cleaned = cleaned.replace('\x00', '')
    return cleaned.strip()[:max_length]

def validate_amount(amount: Decimal, min_amount: Optional[Decimal] = None, max_amount: Optional[Decimal] = None) -> bool:
    # Validate that amount is positive and within optional bounds
    if amount is None or amount <= Decimal('0'):
        return False
    if min_amount is not None and amount < min_amount:
        return False
    if max_amount is not None and amount > max_amount:
        return False
    return True
