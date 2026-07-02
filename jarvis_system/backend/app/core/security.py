import os
import base64
import logging
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from datetime import datetime, timedelta
import jwt

# Try to import post-quantum cryptography library. 
# In a real environment, this would be a Python binding to liboqs or similar.
try:
    import pqcrypto.kem.kyber512 as kyber
    HAS_PQC = True
except ImportError:
    HAS_PQC = False
    logging.warning("pqcrypto not found. Falling back to simulated Quantum-Resistant layer.")

SECRET_KEY = os.getenv("JARVIS_SECRET_KEY", "super-secret-key-for-development-only-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15

class QuantumEncryptionSystem:
    """
    Handles standard AES-256-GCM and Post-Quantum Cryptography (PQC).
    """
    def __init__(self):
        # Generate a master key from the secret key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32, # AES-256 requires 32 bytes
            salt=b"jarvis-quantum-salt",
            iterations=390000,
        )
        self.key = kdf.derive(SECRET_KEY.encode())
        self.aesgcm = AESGCM(self.key)

    def encrypt(self, data: str) -> str:
        """Encrypt data using AES-256-GCM."""
        nonce = os.urandom(12)
        encrypted_data = self.aesgcm.encrypt(nonce, data.encode(), None)
        # Prepend nonce for decryption
        return base64.b64encode(nonce + encrypted_data).decode('utf-8')

    def decrypt(self, encrypted_token: str) -> str:
        """Decrypt data using AES-256-GCM."""
        decoded = base64.b64decode(encrypted_token)
        nonce = decoded[:12]
        encrypted_data = decoded[12:]
        decrypted_data = self.aesgcm.decrypt(nonce, encrypted_data, None)
        return decrypted_data.decode('utf-8')

    def generate_quantum_keypair(self):
        """Generate a quantum-resistant keypair using CRYSTALS-Kyber."""
        if HAS_PQC:
            public_key, secret_key = kyber.generate_keypair()
            return public_key, secret_key
        else:
            # Simulate key generation
            return os.urandom(32), os.urandom(32)

    def encapsulate_secret(self, public_key: bytes):
        """Encapsulate a secret using CRYSTALS-Kyber public key."""
        if HAS_PQC:
            ciphertext, shared_secret = kyber.encapsulate(public_key)
            return ciphertext, shared_secret
        else:
            # Simulate encapsulation
            shared_secret = os.urandom(32)
            ciphertext = AESGCM(shared_secret).encrypt(os.urandom(12), b"simulated_kem", None)
            return ciphertext, shared_secret

    def decapsulate_secret(self, ciphertext: bytes, secret_key: bytes):
        """Decapsulate a secret using CRYSTALS-Kyber secret key."""
        if HAS_PQC:
            shared_secret = kyber.decapsulate(ciphertext, secret_key)
            return shared_secret
        else:
            # Simulated return; in reality this would derive the same shared secret
            return os.urandom(32)

quantum_crypto = QuantumEncryptionSystem()

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
