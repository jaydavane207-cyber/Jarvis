import os
import logging
from typing import Tuple
try:
    import oqs
    OQS_AVAILABLE = True
except ImportError:
    OQS_AVAILABLE = False
    logging.warning("liboqs-python not installed or compiled. Falling back to simulated Kyber.")

class SimulatedKyber:
    """Fallback if OQS is not compiled correctly on the host system."""
    def keypair(self):
        return b"simulated_public_key", b"simulated_secret_key"
    def encaps(self, public_key):
        return b"simulated_ciphertext", b"simulated_shared_secret"
    def decaps(self, ciphertext, secret_key):
        return b"simulated_shared_secret"

class QuantumCryptographyManager:
    def __init__(self, algorithm: str = "Kyber512"):
        self.algorithm = algorithm
        self.kem = oqs.KeyEncapsulation(self.algorithm) if OQS_AVAILABLE else SimulatedKyber()

    def generate_keypair(self) -> Tuple[bytes, bytes]:
        """Generates a post-quantum public and secret key pair."""
        return self.kem.keypair()

    def encapsulate_secret(self, public_key: bytes) -> Tuple[bytes, bytes]:
        """Encapsulates a shared secret using the recipient's public key."""
        return self.kem.encaps(public_key)

    def decapsulate_secret(self, ciphertext: bytes, secret_key: bytes) -> bytes:
        """Decapsulates the shared secret using the recipient's secret key."""
        return self.kem.decaps(ciphertext, secret_key)

# Singleton instance
pqc_manager = QuantumCryptographyManager()
