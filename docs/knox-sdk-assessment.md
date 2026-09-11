# Samsung Knox SDK: what it would add to Local MDM, and what it would cost

Read on 2026-09-11 from docs.samsungknox.com (the SDK reference package index,
the RestrictionPolicy, SystemManager, ApplicationPolicy, KioskMode and
KnoxEnterpriseLicenseManager references, the licensing FAQ, the ProKiosk
overview, knowledge base article KBA-1710 on SystemUpdatePolicy, and the
E-FOTA FAQ). Statements marked verified are quoted from those pages; the
rest is inference and says so.

## The short version

Local MDM's Device Owner path already covers kiosk, restrictions, app install,
Wi-Fi provisioning and the automatic install policy with public Android APIs
and no vendor dependency. The Knox SDK adds four things that matter for a wall
tablet, and every one of them carries a Samsung dependency the project was
designed to avoid:

| Capability | Android Device Owner (what Local MDM uses) | Knox SDK | Worth it here |
| --- | --- | --- | --- |
| Force firmware downloads, not only installs | `SystemUpdatePolicy` automatic: "does not force the device to download updates; it can only install downloaded updates" (KBA-1710, verified) | Only through Knox E-FOTA, a paid per-seat cloud service with its own client and console (E-FOTA FAQ, verified) | No: cloud, paid, per seat |
| Block or allow OTA at all | not available | `RestrictionPolicy.allowOTAUpgrade(boolean)`: "If disabled, all possible OTA upgrade requests (user initiated, server initiated, and system initiated) are blocked" (verified) | No: the goal is faster updates, not blocking them |
| Hide the navigation bar and hardware keys | lock task with `LOCK_TASK_FEATURE_HOME` keeps the bar but neutralizes it | `KioskMode.hideNavigationBar`, `allowHardwareKeys`: deprecated at API level 33, "not available on Android 16 and higher" (verified); replacement is ProKiosk (`ProKioskManager.startProKioskMode(packageName, passCode)`) behind `CUSTOM_PROKIOSK` and a KPE license | Not on Android 16 tablets without ProKiosk, and ProKiosk needs a license activation |
| Silent APK install | `PackageInstaller` as Device Owner (working, verified on the Tab A11+) | `ApplicationPolicy.installApplication(apkFilePath, boolean)` | No: same result, extra dependency |
| Wi-Fi profiles | `WifiManager.addNetworkPrivileged` (working) | `com.samsung.android.knox.net.wifi.WifiPolicy` | No |
| Device attestation and audit log | none in Local MDM today | `com.samsung.android.knox.integrity`, `com.samsung.android.knox.log` | Maybe, for HA SOC evidence, in a later phase |

## The licensing dependency, stated plainly

Every Knox SDK call above `Standard` needs a Knox Platform for Enterprise
(KPE) license key activated on the device through
`KnoxEnterpriseLicenseManager.activateLicense(key)`, which reports back over
the `ACTION_LICENSE_STATUS` broadcast with `EXTRA_LICENSE_ERROR_CODE` and
`EXTRA_LICENSE_GRANTED_PERMISSIONS` (verified from the class reference). The
licensing FAQ states "The KPE Premium license is a free license that provides
access to both Standard and Premium Knox Platform for Enterprise features"
(verified), keys come from the Knox Partner Program dashboard or the Knox
Developer portal (verified), and "Commercial licenses are valid for two years"
(verified). What the pages do not say, and what matters here: activation is a
call to Samsung's license server from the tablet, so a Knox-based DPC has a
cloud dependency at provisioning time and again at renewal, and a Knox Partner
Program account is a business registration. Whether activation needs periodic
re-validation with network access is not stated on the pages read; treat it as
unverified and assume yes.

## Firmware updates, the honest position

Two vendor statements bound what any DPC can do on a Samsung tablet without
E-FOTA:

1. KBA-1710: with `TYPE_INSTALL_AUTOMATIC` "your devices will immediately
   install any downloaded updates", but "part of Samsung's firmware-over-the-air
   (FOTA) concept is to allow the device user to pause downloads", and the API
   "does not force the device to download updates". Samsung's recommendation
   for forced updates is E-FOTA.
2. E-FOTA FAQ: paid subscription, 90 day trial for up to 30 devices, per-seat
   under Knox Suite, cloud console plus an on-device client.

So Local MDM's `auto_os_updates` flag already does everything a local
controller can: whatever Samsung's updater downloads is installed without a
prompt. The Tab A11+ moved from build X230XXU4BZE8 to X230XXS5BZF2 during the
qualification day; whether the automatic policy or the reset triggered the
download could not be told apart (docs/live_qualification.md). Samsung's
updater also does not report through `getPendingSystemUpdate`, so the
`OS update pending` sensor stays off on One UI (docs/backlog.md).

## Kiosk, the honest position

`KioskMode` is deprecated at API level 33 and its methods are "not available
on Android 16 and higher" (verified), which is exactly the Android version on
the Tab A11+. ProKiosk is the replacement and needs the Knox license plus
`com.samsung.android.knox.permission.CUSTOM_PROKIOSK`. Android lock task,
which Local MDM uses, is the vendor-neutral path and is what survives Android
upgrades; the price is a visible but inert navigation bar.

## Edge cases the Knox references settle

- `allowFactoryReset(false)` (Knox) and `DISALLOW_FACTORY_RESET` (Android)
  both leave recovery-mode wipe possible; `allowFirmwareRecovery(false)` (Knox
  API level 11) would close that too and is therefore on the forbidden side of
  this project's design: a tablet that cannot be recovered by someone holding
  it is the failure mode to avoid.
- `setUsbDebuggingEnabled(false)` and `allowDeveloperMode(false)` (Knox) are
  the Knox spellings of removing the adb recovery path; forbidden for the same
  reason as `no_debugging_features`.
- `allowSettingsChanges(false)` (Knox, API level 2) would hide Settings
  entirely, including Wi-Fi; forbidden.

## Recommendation

Do not add the Knox SDK to Local MDM in this phase. Revisit only for
attestation (`knox.integrity`) or audit export (`knox.log`) as HA SOC evidence
sources, and only if a one-time online license activation per tablet is
acceptable. Firmware forcing on Samsung is E-FOTA or nothing; the design
accepts "installed as soon as Samsung's updater has it" as the ceiling.

Sources: the Knox SDK package index
(docs.samsungknox.com/devref/knox-sdk/reference/packages.html), the
RestrictionPolicy, SystemManager, ApplicationPolicy, KioskMode,
KnoxEnterpriseLicenseManager and ProKioskManager references, the Knox SDK
licensing FAQ, KBA-1710 "SystemUpdatePolicy API update behavior", and the
Knox E-FOTA FAQ.
