import os
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "GST API Engine"
    environment: str = "development"
    database_url: str = "sqlite+pysqlite:///./dev.db"
    redis_url: str = "redis://localhost:6379/0"

    jwt_algorithm: str = "RS256"
    jwt_private_key_path: str = ""
    jwt_public_key_path: str = ""
    jwt_secret: str = "dev-only-change-me"

    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 15

    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # Email configuration
    smtp_host: str = "smtp.hostinger.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    from_email: str = "support@apexbooks.in"
    from_name: str = "ApexBooks"

    model_config = SettingsConfigDict(env_file=str(Path(__file__).parent.parent.parent / ".env"), extra="ignore")

    def get_jwt_private_key(self) -> str:
        if self.jwt_algorithm == "HS256":
            return self.jwt_secret
        if self.environment == "production" and self.jwt_private_key_path:
            path = Path(self.jwt_private_key_path)
            if path.exists():
                return path.read_text()
        return self._get_dev_private_key()

    def get_jwt_public_key(self) -> str:
        if self.jwt_algorithm == "HS256":
            return self.jwt_secret
        if self.environment == "production" and self.jwt_public_key_path:
            path = Path(self.jwt_public_key_path)
            if path.exists():
                return path.read_text()
        return self._get_dev_public_key()

    def _get_dev_private_key(self) -> str:
        """Generate ephemeral RSA key for development. NEVER used in production."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        return key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ).decode()

    def _get_dev_public_key(self) -> str:
        """Generate ephemeral RSA key for development. NEVER used in production."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        return key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()


@lru_cache
def get_settings() -> Settings:
    return Settings()
