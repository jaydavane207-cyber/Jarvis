from cryptography.fernet import Fernet, InvalidToken
from typing import Optional
import pyotp
import qrcode
import io
import base64
from ..config import settings
import logging

logger = logging.getLogger(__name__)

class EncryptionManager:
    def __init__(self):
        self.key = settings.master_key
        self.fernet = Fernet(self.key.encode()) if self.key else None
        
        if not self.key:
            logger.warning("No master_key found in settings. Encryption is disabled (pass-through).")

    def encrypt(self, text: str) -> str:
        """Encrypts a string. Returns the original string if no master key is set."""
        if not text or not self.fernet:
            return text
        try:
            return self.fernet.encrypt(text.encode('utf-8')).decode('utf-8')
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return text

    def decrypt(self, encrypted_text: str) -> str:
        """Decrypts a string. Returns the original string if decryption fails or no key."""
        if not encrypted_text or not self.fernet:
            return encrypted_text
        try:
            return self.fernet.decrypt(encrypted_text.encode('utf-8')).decode('utf-8')
        except InvalidToken:
            # Maybe it's plain text (from before encryption was enabled)
            return encrypted_text
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return encrypted_text

crypto_manager = EncryptionManager()

class MFAManager:
    def __init__(self):
        self.secret = settings.mfa_secret
        
        if not self.secret:
            logger.warning("No mfa_secret found in settings. MFA is effectively disabled.")

    def verify(self, code: str) -> bool:
        """Verifies a 6-digit TOTP code."""
        if not self.secret:
            return True # Allow if MFA not configured
        totp = pyotp.TOTP(self.secret)
        return totp.verify(code)

    def get_provisioning_uri(self) -> str:
        """Gets the provisioning URI for authenticator apps."""
        if not self.secret:
            return ""
        totp = pyotp.TOTP(self.secret)
        return totp.provisioning_uri(name="JARVIS Dashboard", issuer_name="JARVIS")

    def get_qr_code_base64(self) -> str:
        """Generates a base64 encoded QR code for MFA setup."""
        uri = self.get_provisioning_uri()
        if not uri:
            return ""
        
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode("utf-8")

mfa_manager = MFAManager()
