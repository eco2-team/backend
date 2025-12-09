from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import base64

from domains.auth.core.config import get_settings


class KeyManager:
    _private_key = None
    _public_key = None

    @classmethod
    def ensure_keys(cls):
        """Generate RSA key pair if not exists."""
        if cls._private_key:
            return

        settings = get_settings()
        if settings.jwt_private_key_pem:
            try:
                # Load from settings (Environment Variable / Secrets Manager)
                cls._private_key = serialization.load_pem_private_key(
                    settings.jwt_private_key_pem.encode("utf-8"),
                    password=None,
                    backend=default_backend(),
                )
                cls._public_key = cls._private_key.public_key()
                return
            except Exception as e:
                # Log error but fall through to generation for local dev resilience
                print(f"Error loading private key from settings: {e}")

        if not cls._private_key:
            # Fallback: Generate on startup (Note: Tokens invalidate on restart)
            print("Generating ephemeral RSA key pair")
            cls._private_key = rsa.generate_private_key(
                public_exponent=65537, key_size=2048, backend=default_backend()
            )
            cls._public_key = cls._private_key.public_key()

    @classmethod
    def get_private_key(cls):
        cls.ensure_keys()
        return cls._private_key

    @classmethod
    def get_public_key_pem(cls) -> str:
        cls.ensure_keys()
        pem = cls._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return pem.decode("utf-8")

    @classmethod
    def get_jwks(cls) -> dict:
        """Return JWKS (JSON Web Key Set) for Public Key."""
        cls.ensure_keys()
        public_numbers = cls._public_key.public_numbers()

        def to_base64url_uint(val: int) -> str:
            bytes_val = val.to_bytes((val.bit_length() + 7) // 8, byteorder="big")
            return base64.urlsafe_b64encode(bytes_val).decode("utf-8").rstrip("=")

        return {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "kid": "eco2-auth-key-01",
                    "alg": "RS256",
                    "n": to_base64url_uint(public_numbers.n),
                    "e": to_base64url_uint(public_numbers.e),
                }
            ]
        }
