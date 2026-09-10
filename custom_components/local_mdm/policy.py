"""Policy document model and the network-safety guard.

This module has no Home Assistant imports so it can be unit tested and reused
by tooling. The guard is the control-plane half of a two-sided rule; the DPC
refuses the same keys. docs/security.md explains why both sides check.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from .const import POLICY_FLAGS, POLICY_KIOSK_MODE, POLICY_KIOSK_PACKAGES

# Android UserManager restriction names and policy keys that can sever the
# only management path (Wi-Fi, adb). Never accepted, never forwarded.
FORBIDDEN_KEYS: Final[frozenset[str]] = frozenset(
    {
        "no_config_wifi",
        "no_config_tethering",
        "no_network_reset",
        "no_config_mobile_networks",
        "no_airplane_mode",
        "no_debugging_features",
        "no_config_private_dns",
        "no_config_vpn",
        "wifi_disabled",
        "network_settings_blocked",
        "adb_disabled",
        "user_restrictions",
        "global_settings",
        "secure_settings",
    }
)

DPC_PACKAGE: Final = "com.trooperthorn.localmdm"


class UnsafePolicyError(ValueError):
    """Raised for a policy that could remove the management path."""


class InvalidPolicyError(ValueError):
    """Raised for a policy with unknown keys or wrong value types."""


def default_policy() -> dict[str, Any]:
    """Return the least restrictive policy: every flag off, no kiosk packages."""
    policy: dict[str, Any] = dict.fromkeys(POLICY_FLAGS, False)
    policy[POLICY_KIOSK_PACKAGES] = []
    return policy


def validate_policy(policy: Mapping[str, Any]) -> dict[str, Any]:
    """Return a normalized copy of ``policy`` or raise.

    The forbidden-key check runs before the unknown-key check so a forbidden
    key is reported as unsafe rather than merely unknown.
    """
    forbidden = FORBIDDEN_KEYS.intersection(policy)
    if forbidden:
        raise UnsafePolicyError(
            f"Policy keys {sorted(forbidden)} can sever the management path and are refused"
        )

    allowed = set(POLICY_FLAGS) | {POLICY_KIOSK_PACKAGES}
    unknown = set(policy) - allowed
    if unknown:
        raise InvalidPolicyError(f"Unknown policy keys: {sorted(unknown)}")

    normalized = default_policy()
    for key in POLICY_FLAGS:
        if key in policy:
            value = policy[key]
            if not isinstance(value, bool):
                raise InvalidPolicyError(f"{key} must be a boolean, got {value!r}")
            normalized[key] = value

    packages = policy.get(POLICY_KIOSK_PACKAGES, [])
    if not isinstance(packages, list) or not all(isinstance(p, str) and p for p in packages):
        raise InvalidPolicyError(f"{POLICY_KIOSK_PACKAGES} must be a list of package names")
    normalized[POLICY_KIOSK_PACKAGES] = sorted(set(packages) - {DPC_PACKAGE})

    if normalized[POLICY_KIOSK_MODE] and not normalized[POLICY_KIOSK_PACKAGES]:
        raise UnsafePolicyError(
            "kiosk_mode requires at least one package in kiosk_packages; "
            "locking the tablet to the DPC alone leaves the operator no application"
        )
    return normalized
