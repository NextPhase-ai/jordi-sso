import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict

class JWTManager:
    def __init__(self, secret_key: str, algorithm: str = "HS256", expiry_seconds: int = 1800):
        """
        Initialize JWT Manager with secret key, algorithm, and expiry duration.
        """
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.expiry_seconds = expiry_seconds

    def create_token(self, email: str, extra_claims: Optional[Dict] = None) -> str:
        """
        Create a JWT token with email and optional extra claims.
        """
        payload = {
            "email": email,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(seconds=self.expiry_seconds)
        }

        if extra_claims:
            payload.update(extra_claims)

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token

    def decode_token(self, token: str) -> Optional[Dict]:
        """
        Decode and validate a JWT token. Returns payload if valid, else None.
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            # Token expired
            return None
        except jwt.InvalidTokenError:
            # Invalid token
            return None
