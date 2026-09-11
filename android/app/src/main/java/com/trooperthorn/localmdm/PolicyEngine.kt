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
import android.content.pm.PackageManager as PM
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
    val isDeviceAdmin: Boolean get() = dpm.isAdminActive(admin)

    /**
     * owner: full Device Owner. admin: active device admin only (the "lite"
     * tier for tablets that cannot take an owner, such as Fire OS); a reduced
     * set of keys is enforced and the rest report `unsupported`. none: nothing
     * is enforced and every key reports `refused`.
     */
    val tier: String get() = when {
        isDeviceOwner -> TIER_OWNER
        isDeviceAdmin -> TIER_ADMIN
        else -> TIER_NONE
    }

    private val canWriteSecureSettings: Boolean
        get() = context.checkSelfPermission(android.Manifest.permission.WRITE_SECURE_SETTINGS) == PM.PERMISSION_GRANTED

    fun apply(policy: Policy, version: Int): Map<String, String> {
        // Persist first: a reboot or crash in the middle of enforcement must
        // not leave the previous policy on disk for BootReceiver to restore.
        store.policy = policy
        store.policyVersion = version
        when (tier) {
            TIER_NONE -> {
                val refused = Policy.FLAG_KEYS.associateWith { "refused" }
                store.enforcement = refused
                return refused
            }
            TIER_ADMIN -> return applyLite(policy)
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
        result[Policy.KEY_ACCOUNTS_LOCKED] =
            restriction(UserManager.DISALLOW_MODIFY_ACCOUNTS, policy.accountsLocked)
        result[Policy.KEY_ADD_USER_BLOCKED] =
            restriction(UserManager.DISALLOW_ADD_USER, policy.addUserBlocked)
        result[Policy.KEY_KIOSK_MODE] = attempt { applyKiosk(policy) }
        result[Policy.KEY_APP_MODE] = applyAppMode(policy)

        store.enforcement = result
        return result
    }

    /**
     * allowlist: suspend every launchable package that is not allowed, so the
     * stock launcher, notifications and Hub Mode keep working while only the
     * listed apps open (a suspended app greys out and shows the system
     * dialog). open: lift whatever this DPC suspended. Never touched: this
     * package, the adb shell, Settings, the system UI, the Play Store (the
     * installer of record, which Android refuses to suspend; install_apps_blocked
     * covers it), any HOME launcher, and the kiosk target (already folded into
     * allowedPackages). A package the platform still refuses is logged and the
     * key reports `limited`, so Home Assistant shows the gap without calling
     * the whole allowlist a failure.
     */
    private fun applyAppMode(policy: Policy): String {
        val pm = context.packageManager
        val wanted: Set<String> = if (policy.appMode == Policy.APP_MODE_ALLOWLIST) {
            val keep = policy.allowedPackages.toMutableSet()
            keep += context.packageName
            keep += ADB_SHELL_PACKAGE
            keep += SETTINGS_PACKAGE
            keep += SYSTEM_UI_PACKAGE
            keep += PLAY_STORE_PACKAGE
            val home = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME)
            keep += pm.queryIntentActivities(home, 0).map { it.activityInfo.packageName }
            val launcher = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
            pm.queryIntentActivities(launcher, 0)
                .map { it.activityInfo.packageName }
                .filter { it !in keep }
                .toSortedSet()
        } else {
            emptySet()
        }
        val before = store.suspendedPackages.toSet()
        val lift = (before - wanted).toTypedArray()
        val hold = wanted.toTypedArray()
        val stuck = mutableListOf<String>()
        val outcome = attempt {
            if (lift.isNotEmpty()) stuck += dpm.setPackagesSuspended(admin, lift, false)
            if (hold.isNotEmpty()) stuck += dpm.setPackagesSuspended(admin, hold, true)
        }
        store.suspendedPackages = (wanted - stuck.toSet()).toList()
        store.unsuspendable = stuck.sorted()
        if (outcome != "applied") return outcome
        if (stuck.isEmpty()) return "applied"
        Log.w(TAG, "Platform refused to change suspension of ${stuck.joinToString()}")
        return LIMITED
    }

    /**
     * Lite tier. Honest ceiling per key on a plain device admin:
     * camera and lockNow are admin policies; stay-awake needs the adb-granted
     * WRITE_SECURE_SETTINGS; Wi-Fi on works below Android 10; kiosk is the
     * HomeWatch foreground poll (usage access) plus screen pinning, reported
     * as `limited` because the user can still unpin. Everything else has no
     * non-owner API and reports `unsupported`, which Home Assistant shows as a
     * tier limit, not an enforcement failure.
     */
    private fun applyLite(policy: Policy): Map<String, String> {
        val result = LinkedHashMap<String, String>()
        for (key in Policy.FLAG_KEYS) result[key] = UNSUPPORTED
        result[Policy.KEY_APP_MODE] = UNSUPPORTED
        result[Policy.KEY_CAMERA_DISABLED] = attempt { dpm.setCameraDisabled(admin, policy.cameraDisabled) }
        result[Policy.KEY_STAY_AWAKE_ON_POWER] = if (!canWriteSecureSettings) UNSUPPORTED else attempt {
            Settings.Global.putString(
                context.contentResolver,
                Settings.Global.STAY_ON_WHILE_PLUGGED_IN,
                if (policy.stayAwakeOnPower) "7" else "0",
            )
        }
        result[Policy.KEY_WIFI_ALWAYS_ON] = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) UNSUPPORTED else attempt {
            if (policy.wifiAlwaysOn && !wifiControl.ensureEnabled()) {
                throw IllegalStateException("setWifiEnabled refused")
            }
        }
        result[Policy.KEY_KIOSK_MODE] = applyLiteKiosk(policy)
        store.enforcement = result
        return result
    }

    private fun applyLiteKiosk(policy: Policy): String {
        val watcher = HomeWatch(context, store)
        if (canWriteSecureSettings) {
            runCatching { Settings.Secure.putString(context.contentResolver, "lock_to_app_enabled", "1") }
        }
        val launched = attempt {
            context.startActivity(
                Intent(context, KioskActivity::class.java)
                    .apply {
                        if (policy.kioskMode) putExtra(KioskActivity.EXTRA_TARGET, policy.kioskPackages.first())
                        else putExtra(KioskActivity.EXTRA_STOP, true)
                    }
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
        }
        return when {
            launched != "applied" -> launched
            !policy.kioskMode -> "applied"
            watcher.granted -> LIMITED
            else -> "failed" // no usage access: nothing brings the launcher back
        }
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
            put("tier", tier)
            put("policy_version", store.policyVersion)
            put("policy", store.policy.toJson())
            put("enforcement", JSONObject(store.enforcement))
            put("lock_task_active", isLockTaskActive())
            put("unsuspendable", org.json.JSONArray(store.unsuspendable))
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
        private const val SETTINGS_PACKAGE = "com.android.settings"
        private const val SYSTEM_UI_PACKAGE = "com.android.systemui"
        private const val PLAY_STORE_PACKAGE = "com.android.vending"
        const val TIER_OWNER = "owner"
        const val TIER_ADMIN = "admin"
        const val TIER_NONE = "none"
        const val LIMITED = "limited"
        const val UNSUPPORTED = "unsupported"
    }
}
