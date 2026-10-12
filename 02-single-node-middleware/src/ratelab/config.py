"""Service settings from ``RATELAB_*`` environment variables."""

import socket
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ratelab.constants import ENV_PREFIX


class ApiSettings(BaseSettings):
    """Where the policies live, who this replica is, and which proxies may set client IPs."""

    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX, env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    replica_id: str = Field(default_factory=socket.gethostname)
    policies_file: Path = Path("policies.yaml")
    trusted_proxy_networks: list[str] = ["127.0.0.1/32", "172.16.0.0/12"]
    allow_listed_api_keys: set[str] = set()


@lru_cache
def get_api_settings() -> ApiSettings:
    return ApiSettings()
