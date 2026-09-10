package com.trooperthorn.localmdm

import org.json.JSONArray
import org.json.JSONObject

/**
 * The policy document shared with the Home Assistant integration.
 * Keys and the forbidden set must match custom_components/local_mdm/policy.py;
 * docs/protocol.md is the contract both sides are written against.
 */
data class Policy(
    val kioskMode: Boolean = false,
    val cameraDisabled: Boolean = false,
    val screenCaptureDisabled: Boolean = false,
    val statusBarDisabled: Boolean = false,
    val installAppsBlocked: Boolean = false,
    val uninstallAppsBlocked: Boolean = false,
    val usbFileTransferBlocked: Boolean = false,
    val adjustVolumeBlocked: Boolean = false,
    val safeBootBlocked: Boolean = false,
    val factoryResetBlocked: Boolean = false,
    val autoOsUpdates: Boolean = false,
    val stayAwakeOnPower: Boolean = false,
    val kioskPackages: List<String> = emptyList(),
) {
    fun toJson(): JSONObject = JSONObject().apply {
        put(KEY_KIOSK_MODE, kioskMode)
        put(KEY_CAMERA_DISABLED, cameraDisabled)
        put(KEY_SCREEN_CAPTURE_DISABLED, screenCaptureDisabled)
        put(KEY_STATUS_BAR_DISABLED, statusBarDisabled)
        put(KEY_INSTALL_APPS_BLOCKED, installAppsBlocked)
        put(KEY_UNINSTALL_APPS_BLOCKED, uninstallAppsBlocked)
        put(KEY_USB_FILE_TRANSFER_BLOCKED, usbFileTransferBlocked)
        put(KEY_ADJUST_VOLUME_BLOCKED, adjustVolumeBlocked)
        put(KEY_SAFE_BOOT_BLOCKED, safeBootBlocked)
        put(KEY_FACTORY_RESET_BLOCKED, factoryResetBlocked)
        put(KEY_AUTO_OS_UPDATES, autoOsUpdates)
        put(KEY_STAY_AWAKE_ON_POWER, stayAwakeOnPower)
        put(KEY_KIOSK_PACKAGES, JSONArray(kioskPackages))
    }

    companion object {
        const val KEY_KIOSK_MODE = "kiosk_mode"
        const val KEY_CAMERA_DISABLED = "camera_disabled"
        const val KEY_SCREEN_CAPTURE_DISABLED = "screen_capture_disabled"
        const val KEY_STATUS_BAR_DISABLED = "status_bar_disabled"
        const val KEY_INSTALL_APPS_BLOCKED = "install_apps_blocked"
        const val KEY_UNINSTALL_APPS_BLOCKED = "uninstall_apps_blocked"
        const val KEY_USB_FILE_TRANSFER_BLOCKED = "usb_file_transfer_blocked"
        const val KEY_ADJUST_VOLUME_BLOCKED = "adjust_volume_blocked"
        const val KEY_SAFE_BOOT_BLOCKED = "safe_boot_blocked"
        const val KEY_FACTORY_RESET_BLOCKED = "factory_reset_blocked"
        const val KEY_AUTO_OS_UPDATES = "auto_os_updates"
        const val KEY_STAY_AWAKE_ON_POWER = "stay_awake_on_power"
        const val KEY_KIOSK_PACKAGES = "kiosk_packages"

        val FLAG_KEYS = listOf(
            KEY_KIOSK_MODE, KEY_CAMERA_DISABLED, KEY_SCREEN_CAPTURE_DISABLED,
            KEY_STATUS_BAR_DISABLED, KEY_INSTALL_APPS_BLOCKED, KEY_UNINSTALL_APPS_BLOCKED,
            KEY_USB_FILE_TRANSFER_BLOCKED, KEY_ADJUST_VOLUME_BLOCKED, KEY_SAFE_BOOT_BLOCKED,
            KEY_FACTORY_RESET_BLOCKED, KEY_AUTO_OS_UPDATES, KEY_STAY_AWAKE_ON_POWER,
        )

        /** Keys that could sever Wi-Fi or adb, the only recovery paths. Refused on sight. */
        val FORBIDDEN_KEYS = setOf(
            "no_config_wifi", "no_config_tethering", "no_network_reset",
            "no_config_mobile_networks", "no_airplane_mode", "no_debugging_features",
            "no_config_private_dns", "no_config_vpn", "wifi_disabled",
            "network_settings_blocked", "adb_disabled", "user_restrictions",
            "global_settings", "secure_settings",
        )

        class UnsafePolicy(message: String) : IllegalArgumentException(message)
        class InvalidPolicy(message: String) : IllegalArgumentException(message)

        fun fromJson(json: JSONObject, selfPackage: String): Policy {
            val keys = json.keys().asSequence().toSet()
            val forbidden = keys.intersect(FORBIDDEN_KEYS)
            if (forbidden.isNotEmpty()) {
                throw UnsafePolicy("Refusing keys that can sever the management path: $forbidden")
            }
            val unknown = keys - FLAG_KEYS.toSet() - KEY_KIOSK_PACKAGES
            if (unknown.isNotEmpty()) throw InvalidPolicy("Unknown policy keys: $unknown")

            fun flag(key: String): Boolean {
                if (!json.has(key)) return false
                val value = json.get(key)
                if (value !is Boolean) throw InvalidPolicy("$key must be a boolean")
                return value
            }

            val packages = mutableSetOf<String>()
            json.optJSONArray(KEY_KIOSK_PACKAGES)?.let { array ->
                for (i in 0 until array.length()) {
                    val name = array.optString(i, "")
                    if (name.isEmpty()) throw InvalidPolicy("kiosk_packages entries must be package names")
                    if (name != selfPackage) packages.add(name)
                }
            }
            val policy = Policy(
                kioskMode = flag(KEY_KIOSK_MODE),
                cameraDisabled = flag(KEY_CAMERA_DISABLED),
                screenCaptureDisabled = flag(KEY_SCREEN_CAPTURE_DISABLED),
                statusBarDisabled = flag(KEY_STATUS_BAR_DISABLED),
                installAppsBlocked = flag(KEY_INSTALL_APPS_BLOCKED),
                uninstallAppsBlocked = flag(KEY_UNINSTALL_APPS_BLOCKED),
                usbFileTransferBlocked = flag(KEY_USB_FILE_TRANSFER_BLOCKED),
                adjustVolumeBlocked = flag(KEY_ADJUST_VOLUME_BLOCKED),
                safeBootBlocked = flag(KEY_SAFE_BOOT_BLOCKED),
                factoryResetBlocked = flag(KEY_FACTORY_RESET_BLOCKED),
                autoOsUpdates = flag(KEY_AUTO_OS_UPDATES),
                stayAwakeOnPower = flag(KEY_STAY_AWAKE_ON_POWER),
                kioskPackages = packages.sorted(),
            )
            if (policy.kioskMode && policy.kioskPackages.isEmpty()) {
                throw UnsafePolicy("kiosk_mode requires at least one package in kiosk_packages")
            }
            return policy
        }
    }
}
