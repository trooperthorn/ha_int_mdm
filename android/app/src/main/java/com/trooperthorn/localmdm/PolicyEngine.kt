package com.trooperthorn.localmdm

import android.app.ActivityManager
import android.app.admin.DevicePolicyManager
import android.app.admin.SystemUpdatePolicy
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.BatteryManager
import android.os.Build
import android.provider.Settings
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

    val wifiControl = Wifi(context)

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
        result[Policy.KEY_AUTO_OS_UPDATES] = attempt {
            dpm.setSystemUpdatePolicy(
                admin,
                if (policy.autoOsUpdates) SystemUpdatePolicy.createAutomaticInstallPolicy() else null,
            )
        }
        result[Policy.KEY_STAY_AWAKE_ON_POWER] = attempt {
            // 7 = AC | USB | wireless (BatteryManager.BATTERY_PLUGGED_* bits).
            dpm.setGlobalSetting(
                admin,
                Settings.Global.STAY_ON_WHILE_PLUGGED_IN,
                if (policy.stayAwakeOnPower) "7" else "0",
            )
        }
        result[Policy.KEY_WIFI_ALWAYS_ON] = attempt {
            if (policy.wifiAlwaysOn && !wifiControl.ensureEnabled()) {
                throw IllegalStateException("setWifiEnabled refused")
            }
        }
        result[Policy.KEY_KIOSK_MODE] = attempt { applyKiosk(policy) }

        store.policy = policy
        store.policyVersion = version
        store.enforcement = result
        return result
    }

    private fun applyKiosk(policy: Policy) {
        // The DPC stays in the allow list so KioskActivity can start and stop
        // lock task mode; the guard already removed it from the user's list.
        // com.android.shell owns the "Allow USB debugging?" dialog; without it in
        // the allow list, lock task hides the prompt and adb (the recovery path)
        // is unusable after a reboot. Found on a Galaxy Tab A11+ on 2026-09-11.
        val allowed = (policy.kioskPackages + context.packageName + ADB_SHELL_PACKAGE).toTypedArray()
        dpm.setLockTaskPackages(admin, if (policy.kioskMode) allowed else emptyArray())
        // While kiosk is on, KioskActivity is the HOME app so a reboot or a
        // home press lands back in lock task with the target application.
        dpm.clearPackagePersistentPreferredActivities(admin, context.packageName)
        val homeAlias = ComponentName(context, "${context.packageName}.KioskHome")
        context.packageManager.setComponentEnabledSetting(
            homeAlias,
            if (policy.kioskMode) PackageManager.COMPONENT_ENABLED_STATE_ENABLED
            else PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
            PackageManager.DONT_KILL_APP,
        )
        if (policy.kioskMode) {
            val home = IntentFilter(Intent.ACTION_MAIN).apply {
                addCategory(Intent.CATEGORY_HOME)
                addCategory(Intent.CATEGORY_DEFAULT)
            }
            dpm.addPersistentPreferredActivity(admin, home, homeAlias)
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

    fun reboot(): Boolean = try {
        dpm.reboot(admin)
        true
    } catch (err: RuntimeException) {
        Log.e(TAG, "reboot refused: ${err.message}")
        false
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
            put(
                "network",
                JSONObject()
                    .put("wifi_connected", Network.isWifiConnected(context))
                    .put("wifi_enabled", wifiControl.isEnabled())
                    .put("ssid", wifiControl.connectedSsid() ?: JSONObject.NULL),
            )
            put("os", osInfo())
            put("system_update", systemUpdateInfo())
            put("installed", installedVersions())
            store.lastInstall?.let { put("last_install", it) }
            put("reported_at", Instant.now().toString())
        }
    }

    private fun osInfo(): JSONObject = JSONObject()
        .put("release", Build.VERSION.RELEASE)
        .put("sdk", Build.VERSION.SDK_INT)
        .put("security_patch", Build.VERSION.SECURITY_PATCH)
        .put("build", Build.DISPLAY)
        .put("model", Build.MODEL)
        .put("manufacturer", Build.MANUFACTURER)

    private fun systemUpdateInfo(): JSONObject {
        val info = JSONObject()
        if (!isDeviceOwner) return info.put("pending", JSONObject.NULL)
        val policy = runCatching { dpm.systemUpdatePolicy }.getOrNull()
        info.put("policy", policy?.policyType ?: 0)
        val pending = runCatching { dpm.getPendingSystemUpdate(admin) }.getOrNull()
        info.put("pending", pending != null)
        if (pending != null) {
            info.put("received_at", Instant.ofEpochMilli(pending.receivedTime).toString())
            info.put("security_patch_state", pending.securityPatchState)
        }
        return info
    }

    /** Installed version of every kiosk package, so Home Assistant can compare with a release. */
    private fun installedVersions(): JSONObject {
        val out = JSONObject()
        for (pkg in store.policy.kioskPackages) {
            val name = runCatching {
                context.packageManager.getPackageInfo(pkg, 0).versionName
            }.getOrNull()
            out.put(pkg, name ?: JSONObject.NULL)
        }
        return out
    }

    companion object {
        private const val TAG = "LocalMdm.Policy"
        private const val ADB_SHELL_PACKAGE = "com.android.shell"
    }
}
