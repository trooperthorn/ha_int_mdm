package com.trooperthorn.localmdm

import android.app.ActivityManager
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.BatteryManager
import android.os.UserManager
import android.util.Log
import java.time.Instant
import org.json.JSONObject

/**
 * Translates a Policy into DevicePolicyManager calls and records, per key,
 * whether the call succeeded. A failure on one key never stops the others;
 * Home Assistant sees the per-key result and raises the problem sensor.
 */
class PolicyEngine(private val context: Context, private val store: PolicyStore) {
    private val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
    private val admin = ComponentName(context, MdmDeviceAdminReceiver::class.java)

    val isDeviceOwner: Boolean get() = dpm.isDeviceOwnerApp(context.packageName)

    fun apply(policy: Policy, version: Int): Map<String, String> {
        if (!isDeviceOwner) {
            val refused = Policy.FLAG_KEYS.associateWith { "refused" }
            store.enforcement = refused
            return refused
        }
        val result = LinkedHashMap<String, String>()

        result[Policy.KEY_CAMERA_DISABLED] = attempt { dpm.setCameraDisabled(admin, policy.cameraDisabled) }
        result[Policy.KEY_SCREEN_CAPTURE_DISABLED] =
            attempt { dpm.setScreenCaptureDisabled(admin, policy.screenCaptureDisabled) }
        result[Policy.KEY_STATUS_BAR_DISABLED] =
            attempt { dpm.setStatusBarDisabled(admin, policy.statusBarDisabled) }
        result[Policy.KEY_INSTALL_APPS_BLOCKED] =
            restriction(UserManager.DISALLOW_INSTALL_APPS, policy.installAppsBlocked)
        result[Policy.KEY_UNINSTALL_APPS_BLOCKED] =
            restriction(UserManager.DISALLOW_UNINSTALL_APPS, policy.uninstallAppsBlocked)
        result[Policy.KEY_USB_FILE_TRANSFER_BLOCKED] =
            restriction(UserManager.DISALLOW_USB_FILE_TRANSFER, policy.usbFileTransferBlocked)
        result[Policy.KEY_ADJUST_VOLUME_BLOCKED] =
            restriction(UserManager.DISALLOW_ADJUST_VOLUME, policy.adjustVolumeBlocked)
        result[Policy.KEY_SAFE_BOOT_BLOCKED] =
            restriction(UserManager.DISALLOW_SAFE_BOOT, policy.safeBootBlocked)
        result[Policy.KEY_FACTORY_RESET_BLOCKED] =
            restriction(UserManager.DISALLOW_FACTORY_RESET, policy.factoryResetBlocked)
        result[Policy.KEY_KIOSK_MODE] = attempt { applyKiosk(policy) }

        store.policy = policy
        store.policyVersion = version
        store.enforcement = result
        return result
    }

    private fun applyKiosk(policy: Policy) {
        // The DPC stays in the allow list so KioskActivity can start and stop
        // lock task mode; the guard already removed it from the user's list.
        val allowed = (policy.kioskPackages + context.packageName).toTypedArray()
        dpm.setLockTaskPackages(admin, if (policy.kioskMode) allowed else emptyArray())
        if (policy.kioskMode) {
            dpm.setLockTaskFeatures(
                admin,
                DevicePolicyManager.LOCK_TASK_FEATURE_HOME or
                    DevicePolicyManager.LOCK_TASK_FEATURE_NOTIFICATIONS or
                    DevicePolicyManager.LOCK_TASK_FEATURE_SYSTEM_INFO,
            )
            context.startActivity(
                Intent(context, KioskActivity::class.java)
                    .putExtra(KioskActivity.EXTRA_TARGET, policy.kioskPackages.first())
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
        } else {
            context.startActivity(
                Intent(context, KioskActivity::class.java)
                    .putExtra(KioskActivity.EXTRA_STOP, true)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
        }
    }

    private fun restriction(name: String, enabled: Boolean): String = attempt {
        if (enabled) dpm.addUserRestriction(admin, name) else dpm.clearUserRestriction(admin, name)
    }

    private fun attempt(block: () -> Unit): String = try {
        block()
        "applied"
    } catch (err: SecurityException) {
        Log.e(TAG, "DevicePolicyManager refused: ${err.message}")
        "refused"
    } catch (err: RuntimeException) {
        Log.e(TAG, "DevicePolicyManager failed: ${err.message}")
        "failed"
    }

    fun lockNow(): Boolean = try {
        dpm.lockNow()
        true
    } catch (err: SecurityException) {
        Log.e(TAG, "lockNow refused: ${err.message}")
        false
    }

    fun isLockTaskActive(): Boolean {
        val am = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        return am.lockTaskModeState != ActivityManager.LOCK_TASK_MODE_NONE
    }

    fun status(): JSONObject {
        val battery = context.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        val level = battery.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
        val charging = battery.isCharging
        return JSONObject().apply {
            put("device_id", store.deviceId)
            put("dpc_version", BuildConfig.VERSION_NAME)
            put("is_device_owner", isDeviceOwner)
            put("policy_version", store.policyVersion)
            put("policy", store.policy.toJson())
            put("enforcement", JSONObject(store.enforcement))
            put("lock_task_active", isLockTaskActive())
            put("battery", JSONObject().put("level", level).put("charging", charging))
            put("network", JSONObject().put("wifi_connected", Network.isWifiConnected(context)))
            put("reported_at", Instant.now().toString())
        }
    }

    companion object {
        private const val TAG = "LocalMdm.Policy"
    }
}
