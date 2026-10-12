"""Who is calling: API key, then user, then client IP."""

import ipaddress
from collections.abc import Iterable

from starlette.requests import Request

from ratelab.constants import (
    API_KEY_HEADER,
    CALLER_KEY_PREFIX_API_KEY,
    CALLER_KEY_PREFIX_IP,
    CALLER_KEY_PREFIX_USER,
    FORWARDED_FOR_HEADER,
    UNKNOWN_CLIENT_ADDRESS,
    USER_ID_HEADER,
)


class CallerKeyExtractor:
    """Builds the key a request is counted under.

    ``X-Forwarded-For`` is only believed when the connection comes from a trusted proxy;
    otherwise any client could pick its own IP and dodge an IP limit.
    """

    def __init__(self, trusted_proxy_networks: Iterable[str]) -> None:
        self._trusted_networks = [
            ipaddress.ip_network(network) for network in trusted_proxy_networks
        ]

    def extract_caller_key(self, request: Request) -> str:
        api_key = request.headers.get(API_KEY_HEADER)
        if api_key:
            return self.extract_caller_key_for_api_key(api_key)
        user_id = request.headers.get(USER_ID_HEADER)
        if user_id:
            return f"{CALLER_KEY_PREFIX_USER}:{user_id}"
        return f"{CALLER_KEY_PREFIX_IP}:{self.extract_client_address(request)}"

    def extract_caller_key_for_api_key(self, api_key: str) -> str:
        return f"{CALLER_KEY_PREFIX_API_KEY}:{api_key}"

    def extract_client_address(self, request: Request) -> str:
        peer_address = request.client.host if request.client else UNKNOWN_CLIENT_ADDRESS
        forwarded_for = request.headers.get(FORWARDED_FOR_HEADER)
        if forwarded_for and self.is_trusted_proxy(peer_address):
            return forwarded_for.split(",")[0].strip()
        return peer_address

    def is_trusted_proxy(self, address: str) -> bool:
        try:
            parsed_address = ipaddress.ip_address(address)
        except ValueError:
            return False
        return any(parsed_address in network for network in self._trusted_networks)
