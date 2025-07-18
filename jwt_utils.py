import jwt
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class JWTManager:
    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        expiry_seconds: int = 1800,
        leeway_seconds: int = 10
    ):
        """
        Initialize JWT Manager with security settings.
        """
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.expiry_seconds = expiry_seconds
        self.leeway = leeway_seconds

    def create_token(self, email: str, extra_claims: Optional[Dict] = None) -> str:
        """
        Create a signed JWT with optional additional claims.
        """
        now = datetime.utcnow()
        payload = {
            "email": email,
            "iat": now,
            "exp": now + timedelta(seconds=self.expiry_seconds),
        }

        if extra_claims:
            payload.update(extra_claims)

        try:
            token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
            return token
        except Exception as e:
            logger.exception("Failed to generate JWT")
            raise RuntimeError("JWT creation failed") from e

    def decode_token(self, token: str) -> Optional[Dict]:
        """
        Decode a JWT. Returns payload if valid, else None.
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                leeway=self.leeway,
                options={
                    "require": ["exp", "iat"],
                    "verify_exp": True
                }
            )
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("JWT expired")
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT: {str(e)}")
        except Exception as e:
            logger.exception("Unexpected error decoding JWT")

        return None

    def is_token_valid(self, token: str) -> bool:
        """
        Simple check for token validity.
        """
        return self.decode_token(token) is not None
