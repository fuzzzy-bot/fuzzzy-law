"""
Connector Access Service — who is calling the law connector, and how much.

Two modes, chosen by ``settings.connector_access_mode`` so that whoever runs
the connector can choose:

* ``open``    — anyone; the caller is their IP address, limited per minute.
  An IPv6 caller is counted by its /64 network (one household or phone holds
  a whole /64), and an address inside ``connector_shared_ip_ranges`` (an AI
  provider calling for many people at once) gets the higher shared limit.
* ``api_key`` — ``Authorization: Bearer <key>``; keys are stored only as
  SHA-256 hashes in ``connector_api_keys_file``, each with its own user name
  and optional daily quota.
Key holders get a per-minute limit and a daily quota. Account sign-in through
OAuth (what ChatGPT's and Claude's connector screens use instead of keys) is
left for later, once a sign-in service is chosen.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config.settings import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

MINUTE = 60.0
DAY = 86_400.0


@dataclass(frozen=True)
class ConnectorCaller:
    """An admitted caller and the limits that apply to them."""

    caller_id: str
    per_minute: int
    daily_quota: int | None  # None = no daily quota (open mode)


class ConnectorAccessDenied(Exception):
    """The request carries no usable credential for the configured mode."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def _rate_limit_address(client_ip: str) -> ipaddress.IPv4Address | ipaddress.IPv6Network | None:
    """The address a caller is counted under, or None when it is not an IP."""
    try:
        address = ipaddress.ip_address(client_ip)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return address.ipv4_mapped
        return ipaddress.ip_network(f"{address}/64", strict=False)
    return address


@lru_cache(maxsize=8)
def _parse_networks(ranges: tuple[str, ...]) -> tuple[Network, ...]:
    networks = []
    for value in ranges:
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            logger.error("connector_shared_range_invalid", value=value)
    return tuple(networks)


def _is_shared(address: ipaddress.IPv4Address | ipaddress.IPv6Network) -> bool:
    """True when the address belongs to a listed AI provider network."""
    for network in _parse_networks(tuple(settings.connector_shared_networks)):
        if address.version != network.version:
            continue
        if isinstance(address, ipaddress.IPv6Network):
            if address.subnet_of(network) or network.subnet_of(address):
                return True
        elif address in network:
            return True
    return False


def hash_key(key: str) -> str:
    """The form a connector API key is stored in."""
    return hashlib.sha256(key.encode()).hexdigest()


def _bearer_token(authorization: str) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ConnectorAccessDenied(
            "connector_auth_required",
            "Sign-in required: send 'Authorization: Bearer <token>'.",
        )
    return token.strip()


class ConnectorAccessService:
    """Resolve a request's caller under the configured access mode."""

    def __init__(self, keys_file: Path | None = None) -> None:
        self._keys_file = keys_file

    def resolve(self, client_ip: str, authorization: str) -> ConnectorCaller:
        """Identify the caller or raise :class:`ConnectorAccessDenied`."""
        mode = settings.connector_access_mode
        if mode == "open":
            address = _rate_limit_address(client_ip)
            shared = address is not None and _is_shared(address)
            return ConnectorCaller(
                caller_id=f"ip:{address if address is not None else client_ip}",
                per_minute=(
                    settings.connector_shared_rate_limit_per_minute
                    if shared else settings.connector_rate_limit_per_minute
                ),
                daily_quota=None,
            )
        return self._caller_from_key(_bearer_token(authorization))

    def _load_keys(self) -> dict[str, dict]:
        path = self._keys_file or settings.connector_api_keys_file
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error("connector_keys_unreadable", path=str(path), error=str(e))
            return {}

    def _caller_from_key(self, key: str) -> ConnectorCaller:
        entry = self._load_keys().get(hash_key(key))
        if not entry:
            raise ConnectorAccessDenied("connector_key_invalid", "This connector key is not valid.")
        return ConnectorCaller(
            caller_id=f"key:{entry.get('user') or hash_key(key)[:12]}",
            per_minute=settings.connector_rate_limit_per_minute,
            daily_quota=int(entry.get("daily_quota") or settings.connector_daily_quota),
        )


_access_service: ConnectorAccessService | None = None


def get_connector_access_service() -> ConnectorAccessService:
    global _access_service
    if _access_service is None:
        _access_service = ConnectorAccessService()
    return _access_service
