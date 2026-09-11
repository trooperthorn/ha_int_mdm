"""Constants for the Local MDM integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "local_mdm"
MANUFACTURER: Final = "trooperthorn"
MODEL: Final = "Android Device Policy Controller"

CONF_TOKEN: Final = "token"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_WEBHOOK_ID: Final = "webhook_id"
CONF_DEVICE_ID: Final = "device_id"

DEFAULT_PORT: Final = 8484
DEFAULT_SCAN_INTERVAL: Final = 60
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 3600
REQUEST_TIMEOUT: Final = 5

# Policy keys exposed as switches; each maps to one DevicePolicyManager call
# in the DPC. docs/protocol.md has the table.
POLICY_KIOSK_MODE: Final = "kiosk_mode"
POLICY_CAMERA_DISABLED: Final = "camera_disabled"
POLICY_SCREEN_CAPTURE_DISABLED: Final = "screen_capture_disabled"
POLICY_STATUS_BAR_DISABLED: Final = "status_bar_disabled"
POLICY_INSTALL_APPS_BLOCKED: Final = "install_apps_blocked"
POLICY_UNINSTALL_APPS_BLOCKED: Final = "uninstall_apps_blocked"
POLICY_USB_FILE_TRANSFER_BLOCKED: Final = "usb_file_transfer_blocked"
POLICY_ADJUST_VOLUME_BLOCKED: Final = "adjust_volume_blocked"
POLICY_SAFE_BOOT_BLOCKED: Final = "safe_boot_blocked"
POLICY_FACTORY_RESET_BLOCKED: Final = "factory_reset_blocked"
POLICY_AUTO_OS_UPDATES: Final = "auto_os_updates"
POLICY_STAY_AWAKE_ON_POWER: Final = "stay_awake_on_power"
POLICY_WIFI_ALWAYS_ON: Final = "wifi_always_on"

POLICY_FLAGS: Final[tuple[str, ...]] = (
    POLICY_KIOSK_MODE,
    POLICY_CAMERA_DISABLED,
    POLICY_SCREEN_CAPTURE_DISABLED,
    POLICY_STATUS_BAR_DISABLED,
    POLICY_INSTALL_APPS_BLOCKED,
    POLICY_UNINSTALL_APPS_BLOCKED,
    POLICY_USB_FILE_TRANSFER_BLOCKED,
    POLICY_ADJUST_VOLUME_BLOCKED,
    POLICY_SAFE_BOOT_BLOCKED,
    POLICY_FACTORY_RESET_BLOCKED,
    POLICY_AUTO_OS_UPDATES,
    POLICY_STAY_AWAKE_ON_POWER,
    POLICY_WIFI_ALWAYS_ON,
)

COMPANION_PACKAGE: Final = "io.homeassistant.companion.android"

POLICY_KIOSK_PACKAGES: Final = "kiosk_packages"

ENFORCEMENT_APPLIED: Final = "applied"
ENFORCEMENT_FAILED: Final = "failed"
ENFORCEMENT_REFUSED: Final = "refused"
ENFORCEMENT_PENDING: Final = "pending"
