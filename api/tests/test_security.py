import base64
from decimal import Decimal
from django.test import TestCase
from stellar_sdk import Keypair
from api.security import (
    validate_stellar_address,
    verify_stellar_signature,
    sanitize_text,
    validate_amount,
)

class SecurityUtilsTest(TestCase):
    def setUp(self):
        self.keypair = Keypair.random()
        self.public_key = self.keypair.public_key

    def test_validate_stellar_address(self):
        self.assertTrue(validate_stellar_address(self.public_key))
        # Invalid prefixes or lengths
        self.assertFalse(validate_stellar_address("S" + self.public_key[1:]))
        self.assertFalse(validate_stellar_address("GSHORT"))
        self.assertFalse(validate_stellar_address(""))
        self.assertFalse(validate_stellar_address(None))
        # Corrupted checksum
        corrupted = self.public_key[:-4] + "AAAA"
        self.assertFalse(validate_stellar_address(corrupted))

    def test_verify_stellar_signature(self):
        message = "AfriCash Test Authentication Challenge"
        raw_signature = self.keypair.sign(message.encode('utf-8'))
        sig_b64 = base64.b64encode(raw_signature).decode('utf-8')
        sig_hex = raw_signature.hex()

        # Both base64 and hex encodings should verify successfully
        self.assertTrue(verify_stellar_signature(self.public_key, message, sig_b64))
        self.assertTrue(verify_stellar_signature(self.public_key, message, sig_hex))

        # Tampered message should fail
        self.assertFalse(verify_stellar_signature(self.public_key, "Tampered Message", sig_b64))

        # Tampered signature should fail
        bad_sig = base64.b64encode(b"0" * 64).decode('utf-8')
        self.assertFalse(verify_stellar_signature(self.public_key, message, bad_sig))

        # Wrong public key should fail
        other_keypair = Keypair.random()
        self.assertFalse(verify_stellar_signature(other_keypair.public_key, message, sig_b64))

    def test_sanitize_text(self):
        html_input = "<script>alert('xss');</script> Lagos Central POS"
        self.assertEqual(sanitize_text(html_input), "alert('xss'); Lagos Central POS")
        self.assertEqual(sanitize_text("<b>Bold</b> Agent"), "Bold Agent")
        self.assertEqual(sanitize_text(None), "")
        self.assertEqual(sanitize_text("   Trimmed Text   "), "Trimmed Text")

    def test_validate_amount(self):
        self.assertTrue(validate_amount(Decimal('10.00'), min_amount=Decimal('5.00'), max_amount=Decimal('100.00')))
        self.assertFalse(validate_amount(Decimal('0')))
        self.assertFalse(validate_amount(Decimal('-5.00')))
        self.assertFalse(validate_amount(Decimal('2.00'), min_amount=Decimal('5.00')))
        self.assertFalse(validate_amount(Decimal('150.00'), max_amount=Decimal('100.00')))
