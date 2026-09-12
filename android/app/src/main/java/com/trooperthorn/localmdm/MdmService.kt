package com.trooperthorn.localmdm

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.Log

/** Foreground service that owns the HTTP server and the heartbeat report. */
class MdmService : Service() {
    private lateinit var store: PolicyStore
    private lateinit var engine: PolicyEngine
    private lateinit var reporter: WebhookReporter
    private var server: HttpServer? = null
    private var homeWatch: HomeWatch? = null
    private var packageWatch: PackageWatch? = null
    private val handler = Handler(Looper.getMainLooper())
    private val heartbeat = object : Runnable {
        override fun run() {
            reporter.report()
            handler.postDelayed(this, HEARTBEAT_MS)
        }
    }

    override fun onCreate() {
        super.onCreate()
        store = PolicyStore(this)
        engine = PolicyEngine(this, store)
        reporter = WebhookReporter(store, engine)
        settleSelfUpdate()
        startForeground(NOTIFICATION_ID, notification())
        // Re-assert the stored policy on every start: user restrictions
        // survive reboot, lock task mode does not.
        if (engine.isDeviceOwner) engine.wifiControl.grantLocationToSelf()
        if (engine.tier != PolicyEngine.TIER_NONE) engine.apply(store.policy, store.policyVersion)
        if (engine.tier == PolicyEngine.TIER_ADMIN) homeWatch = HomeWatch(this, store).also { it.start() }
        if (engine.isDeviceOwner) packageWatch = PackageWatch(this, engine) { reporter.report() }.also { it.start() }
        val installer = Installer(this, store) { reporter.report() }
        server = HttpServer(PORT, store, engine, { reporter.report() }, installer).also {
            try {
                it.start(fi.iki.elonen.NanoHTTPD.SOCKET_READ_TIMEOUT, false)
            } catch (err: java.io.IOException) {
                Log.e(TAG, "Cannot bind port $PORT: ${err.message}")
            }
        }
        handler.post(heartbeat)
    }

    /**
     * A lite-tier update of this app through install_package kills the
     * process before the installer's success callback arrives, so the
     * stored state stays awaiting_user. A version change since the last
     * start is that update having applied; record it as installed.
     */
    private fun settleSelfUpdate() {
        val previous = store.lastSeenVersion
        store.lastSeenVersion = BuildConfig.VERSION_NAME
        val last = store.lastInstall ?: return
        if (last.optString("state") != "awaiting_user") return
        if (previous == null || previous == BuildConfig.VERSION_NAME) return
        store.lastInstall = last
            .put("state", "installed")
            .put("message", "self-update applied ($previous -> ${BuildConfig.VERSION_NAME})")
            .put("package", packageName)
            .put("at", java.time.Instant.now().toString())
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_REPORT) {
            // Lock task state settles a moment after startLockTask/stopLockTask
            // return; report once it has, so Home Assistant sees the real value.
            handler.postDelayed({ reporter.report() }, SETTLE_MS)
        }
        return START_STICKY
    }

    override fun onDestroy() {
        handler.removeCallbacks(heartbeat)
        homeWatch?.stop()
        packageWatch?.stop()
        server?.stop()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun notification(): Notification {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL, getString(R.string.notification_channel), NotificationManager.IMPORTANCE_MIN),
        )
        return Notification.Builder(this, CHANNEL)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(getString(R.string.notification_text, PORT))
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setOngoing(true)
            .build()
    }

    companion object {
        const val PORT = 8484
        private const val TAG = "LocalMdm.Service"
        private const val CHANNEL = "local_mdm"
        private const val NOTIFICATION_ID = 1
        private const val HEARTBEAT_MS = 5 * 60 * 1000L
        private const val SETTLE_MS = 750L
        const val ACTION_REPORT = "com.trooperthorn.localmdm.REPORT"

        fun start(context: Context) {
            context.startForegroundService(Intent(context, MdmService::class.java))
        }

        fun requestReport(context: Context) {
            context.startForegroundService(
                Intent(context, MdmService::class.java).setAction(ACTION_REPORT),
            )
        }
    }
}
