"""Service settings from ``RATELAB_*`` environment variables."""

import socket
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ratelab.constants import ENV_PREFIX


class ApiSettings(BaseSettings):
    """Policies, the Redis connection, and how to behave when Redis is slow or down."""

    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX, env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    replica_id: str = Field(default_factory=socket.gethostname)
    policies_file: Path = Path("policies.yaml")
    algorithm_overrides: dict[str, str] = {}
    trusted_proxy_networks: list[str] = ["127.0.0.1/32", "172.16.0.0/12"]
    allow_listed_api_keys: set[str] = set()

    redis_url: str = "redis://localhost:6379/0"
    redis_timeout_seconds: float = 0.05
    redis_max_connections: int = 200

    breaker_failure_threshold: int = 3
    breaker_open_seconds: float = 2.0
    replica_count_for_local_fallback: int = 3


@lru_cache
def get_api_settings() -> ApiSettings:
    return ApiSettings()
