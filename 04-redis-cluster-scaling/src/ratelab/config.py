"""Service settings from ``RATELAB_*`` environment variables."""

import socket
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ratelab.constants import ENV_PREFIX


class ApiSettings(BaseSettings):
    """Policies, how to reach Redis (one node, a cluster, or via Sentinel), and failure handling."""

    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX, env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    replica_id: str = Field(default_factory=socket.gethostname)
    policies_file: Path = Path("policies.yaml")
    policy_overrides: dict[str, dict[str, Any]] = {}
    trusted_proxy_networks: list[str] = ["127.0.0.1/32", "172.16.0.0/12"]
    allow_listed_api_keys: set[str] = set()

    redis_mode: Literal["single", "cluster", "sentinel"] = "single"
    redis_url: str = "redis://localhost:6379/0"
    redis_cluster_seed_nodes: list[str] = [f"redis-node-{index}:6379" for index in range(1, 7)]
    redis_sentinel_hosts: list[str] = ["sentinel-1:26379", "sentinel-2:26379", "sentinel-3:26379"]
    redis_sentinel_service: str = "ratelab-primary"
    redis_timeout_seconds: float = 0.05
    redis_connect_timeout_seconds: float = 0.25
    redis_max_connections: int = 200

    breaker_failure_threshold: int = 3
    breaker_open_seconds: float = 2.0
    replica_count_for_local_fallback: int = 3


@lru_cache
def get_api_settings() -> ApiSettings:
    return ApiSettings()
