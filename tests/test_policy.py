"""The network-safety guard is the control that prevents a network brick."""

import pytest

from custom_components.local_mdm.policy import (
    DPC_PACKAGE,
    FORBIDDEN_KEYS,
    InvalidPolicyError,
    UnsafePolicyError,
    default_policy,
    validate_policy,
)


def test_default_policy_is_least_restrictive():
    policy = default_policy()
    assert all(value is False for key, value in policy.items() if key != "kiosk_packages")
    assert policy["kiosk_packages"] == []


@pytest.mark.parametrize("key", sorted(FORBIDDEN_KEYS))
def test_every_forbidden_key_is_refused_even_when_false(key):
    with pytest.raises(UnsafePolicyError):
        validate_policy({key: False})


def test_forbidden_beats_unknown():
    with pytest.raises(UnsafePolicyError):
        validate_policy({"no_config_wifi": True, "made_up": 1})


def test_unknown_key_is_invalid():
    with pytest.raises(InvalidPolicyError):
        validate_policy({"made_up": True})


def test_non_boolean_flag_is_invalid():
    with pytest.raises(InvalidPolicyError):
        validate_policy({"camera_disabled": "yes"})


def test_kiosk_without_packages_is_unsafe():
    with pytest.raises(UnsafePolicyError):
        validate_policy({"kiosk_mode": True})


def test_kiosk_with_only_the_dpc_itself_is_unsafe():
    with pytest.raises(UnsafePolicyError):
        validate_policy({"kiosk_mode": True, "kiosk_packages": [DPC_PACKAGE]})


def test_partial_policy_is_normalized_to_full_document():
    result = validate_policy(
        {"camera_disabled": True, "kiosk_packages": ["b.app", "a.app", "a.app"]}
    )
    assert result["camera_disabled"] is True
    assert result["kiosk_mode"] is False
    assert result["kiosk_packages"] == ["a.app", "b.app"]
    assert set(result) == set(default_policy())
