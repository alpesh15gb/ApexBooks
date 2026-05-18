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
        return """-----BEGIN RSA PRIVATE KEY-----
MIIEogIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF8PbnGy0AHB7K3tJ8N5kxR8k8s8m
KkJjOXhLnRPHvJv7B2gF9w0a8yL0z6cW8aW3wRKG2cP8kL3J5p7yT2mL9cG3tK5
uW8vQ9mPxG4sV6yF3L2h9tC5pK2dF7mR8sY9vT3wK5xL4fG6hM2pJ8qR4vK3wL9
xP2mT7nR8sY5vF3wK9L6pM2cJ8qX4tL3wP9mG6hT2pJ8nR3vF5wK9xP4mT3nL6
sY8vT2wK4xP5mF9hJ8nR6wL3vK5xP2mT4nR8sY9vF6wK3xP7mT5nL2sY8vT3wK4
xP9mF2hJ8nR4vL5wK7xP3mT6nL9sY8vT2wAQIDAQABAoIBAFG8xL9P2mT4nR8s
Y9vF3wK5xP7mT2nL6sY8vT4wK3xP9mF5hJ8nR7vL2wK9xP3mT4nR8sY5vF6wK7x
P5mT3nL8sY9vT2wK4xP8mF6hJ8nR3vL5wK3xP2mT7nL9sY8vT3wK5xP9mF4hJ8n
R5vL4wK7xP6mT2nL2sY8vT4wK9xP3mF5hJ8nR8vL6wK5xP4mT7nL9sY8vT2wK3x
P8mF6hJ8nR4vL3wK9xP2mT5nL8sY9vT3wK5xP7mF4hJ8nR6vL5wK7xP9mT3nL2s
Y8vT4wK3xP6mF5hJ8nR7vL4wK5xP8mT2nL9sY9vT2wK4xP9mF3hJ8nR5vL6wK7x
P3mT4nL8sY8vT3wK5xP6mF2hJ8nR8vL3wK9xP7mT5nK9sY9vT4wAQIDAQABAoGB
ANTg5L9P2mT4nR8sY9vF3wK5xP7mT2nL6sY8vT4wK3xP9mF5hJ8nR7vL2wK9xP3m
T4nR8sY5vF6wK7xP5mT3nL8sY9vT2wK4xP8mF6hJ8nR3vL5wK3xP2mT7nL9sY8vT
3wK5xP9mF4hJ8nR5vL4wK7xP6mT2nL2sY8vT4wK9xP3mF5hJ8nR8vL6wK5xP4mT7
nL9sY8vT2wK3xP8mF6hJ8nR4vL3wK9xP2mT5nL8sY9vT3wK5xP7mF4hJ8nR6vL5w
K7xP9mT3nL2sY8vT4wK3xP6mF5hJ8nR7vL4wK5xP8mT2nL9sY9vT2wK4xP9mF3h
J8nR5vL6wAQIDAQABAoGBAOxg5L9P2mT4nR8sY9vF3wK5xP7mT2nL6sY8vT4wK3x
P9mF5hJ8nR7vL2wK9xP3mT4nR8sY5vF6wK7xP5mT3nL8sY9vT2wK4xP8mF6hJ8nR
3vL5wK3xP2mT7nL9sY8vT3wK5xP9mF4hJ8nR5vL4wK7xP6mT2nL2sY8vT4wK9xP3
mF5hJ8nR8vL6wK5xP4mT7nL9sY8vT2wK3xP8mF6hJ8nR4vL3wK9xP2mT5nL8sY9vT
3wK5xP7mF4hJ8nR6vL5wK7xP9mT3nL2sY8vT4wK3xP6mF5hJ8nR7vL4wK5xP8mT2
nL9sY9vT2wK4xP9mF3hJ8nR5vL6wKBgQDmJG4vL9P2mT4nR8sY9vF3wK5xP7mT2nL
6sY8vT4wK3xP9mF5hJ8nR7vL2wK9xP3mT4nR8sY5vF6wK7xP5mT3nL8sY9vT2wK4x
P8mF6hJ8nR3vL5wK3xP2mT7nL9sY8vT3wK5xP9mF4hJ8nR5vL4wK7xP6mT2nL2sY8
vT4wK9xP3mF5hJ8nR8vL6wKBgQDmJG4vL9P2mT4nR8sY9vF3wK5xP7mT2nL6sY8vT
4wK3xP9mF5hJ8nR7vL2wK9xP3mT4nR8sY5vF6wK7xP5mT3nL8sY9vT2wK4xP8mF6
hJ8nR3vL5wK3xP2mT7nL9sY8vT3wK5xP9mF4hJ8nR5vL4wK7xP6mT2nL2sY8vT4w
K9xP3mF5hJ8nR8vL6wKBgQDmJG4vL9P2mT4nR8sY9vF3wK5xP7mT2nL6sY8vT4wK3
xP9mF5hJ8nR7vL2wK9xP3mT4nR8sY5vF6wK7xP5mT3nL8sY9vT2wK4xP8mF6hJ8n
R3vL5wK3xP2mT7nL9sY8vT3wK5xP9mF4hJ8nR5vL4wK7xP6mT2nL2sY8vT4wK9xP
3mF5hJ8nR8vL6wKBgQDmJG4vL9P2mT4nR8sY9vF3wK5xP7mT2nL6sY8vT4wK3xP9
mF5hJ8nR7vL2wK9xP3mT4nR8sY5vF6wK7xP5mT3nL8sY9vT2wK4xP8mF6hJ8nR3vL
5wK3xP2mT7nL9sY8vT3wK5xP9mF4hJ8nR5vL4wK7xP6mT2nL2sY8vT4wK9xP3mF5
hJ8nR8vL6w==
-----END RSA PRIVATE KEY-----"""

    def _get_dev_public_key(self) -> str:
        return """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0Z3VS5JJcds3xfn/ygWy
F8PbnGy0AHB7K3tJ8N5kxR8k8s8mKkJjOXhLnRPHvJv7B2gF9w0a8yL0z6cW8aW3
wRKG2cP8kL3J5p7yT2mL9cG3tK5uW8vQ9mPxG4sV6yF3L2h9tC5pK2dF7mR8sY9v
T3wK5xL4fG6hM2pJ8qR4vK3wL9xP2mT7nR8sY5vF3wK9L6pM2cJ8qX4tL3wP9mG6
hT2pJ8nR3vF5wK9xP4mT3nL6sY8vT2wK4xP5mF9hJ8nR6wL3vK5xP2mT4nR8sY9v
F6wK3xP7mT5nL2sY8vT3wK4xP9mF2hJ8nR4vL5wK7xP3mT6nL9sY8vT2wAQIDAQAB
AoIBAFG8xL9P2mT4nR8sY9vF3wK5xP7mT2nL6sY8vT4wK3xP9mF5hJ8nR7vL2wK9x
P3mT4nR8sY5vF6wK7xP5mT3nL8sY9vT2wK4xP8mF6hJ8nR3vL5wK3xP2mT7nL9sY8v
T3wK5xP9mF4hJ8nR5vL4wK7xP6mT2nL2sY8vT4wK9xP3mF5hJ8nR8vL6wK5xP4mT7
nL9sY8vT2wK3xP8mF6hJ8nR4vL3wK9xP2mT5nL8sY9vT3wK5xP7mF4hJ8nR6vL5w
K7xP9mT3nL2sY8vT4wK3xP6mF5hJ8nR7vL4wK5xP8mT2nL9sY9vT2wK4xP9mF3hJ8
nR5vL6wAQIDAQABAoGBAOxg5L9P2mT4nR8sY9vF3wK5xP7mT2nL6sY8vT4wK3xP9
mF5hJ8nR7vL2wK9xP3mT4nR8sY5vF6wK7xP5mT3nL8sY9vT2wK4xP8mF6hJ8nR3vL
5wK3xP2mT7nL9sY8vT3wK5xP9mF4hJ8nR5vL4wK7xP6mT2nL2sY8vT4wK9xP3mF5
hJ8nR8vL6wKBgQDmJG4vL9P2mT4nR8sY9vF3wK5xP7mT2nL6sY8vT4wK3xP9mF5hJ
8nR7vL2wK9xP3mT4nR8sY5vF6wK7xP5mT3nL8sY9vT2wK4xP8mF6hJ8nR3vL5wK3x
P2mT7nL9sY8vT3wK5xP9mF4hJ8nR5vL4wK7xP6mT2nL2sY8vT4wK9xP3mF5hJ8nR
8vL6w==
-----END PUBLIC KEY-----"""


@lru_cache
def get_settings() -> Settings:
    return Settings()
