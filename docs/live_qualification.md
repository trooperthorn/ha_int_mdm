# Live qualification

The mocked suite proves the integration's half of the contract. These checks
need a real Android system and are recorded here with a date when they pass.

## 2026-09-10: Android 15 emulator (google_apis x86_64) as Device Owner, plus a Motorola razr 2024 (Android 16) as a plain app

Driver: the integration's own `api.py` client from a host Python, with a
host aiohttp receiver standing in for the Home Assistant webhook
(`adb reverse tcp:8123`). Debug APK built with AGP 9.4.0 on Gradle 9.7.1 and
the Android Studio JDK 25.

| Check | How | Result |
| --- | --- | --- |
| DPC becomes Device Owner | `adb shell dpm set-device-owner ...`, app shows "active" | pass (emulator) |
| Foreground service starts on boot | `adb reboot`, then `/v1/status` answers and `dumpsys activity services` lists MdmService | pass |
| Applied policy survives reboot | policy version 50 with camera on before reboot; same after, enforcement all `applied` | pass |
| Status endpoint answers | `curl` with the token; `DeviceStatus.from_payload` parses it | pass (emulator and razr) |
| Bad token | 401 | pass (razr) |
| Webhook URL accepted and triggers a report | `PUT /v1/webhook`, report arrives at the receiver | pass |
| Camera round trip | `PUT /v1/policy` answered in 223 ms; webhook report received 168 ms after the PUT was sent | pass, under 2 s |
| Enforced state | response and report both carry `camera_disabled: applied`; `dumpsys device_policy` shows `disable-camera` | pass |
| Kiosk starts and stops | packages `["com.android.settings"]`, kiosk on gives `lock_task_active: true`; kiosk off releases it | pass |
| Every non-kiosk flag on | nine flags applied, zero failures | pass |
| Forbidden key refused by the client | `UnsafePolicyError`, nothing sent | pass |
| Forbidden key refused by the DPC | direct `PUT` with `no_config_wifi` returns 422 with the guard's message | pass (emulator and razr) |
| Not Device Owner | `PUT /v1/policy` returns 422 "not device owner" | pass (razr) |
| Lock screen action | 200 | pass |
| Wi-Fi remains user-configurable under every policy | `dumpsys user` restriction list contains no `no_config_wifi`, `no_network_reset`, or `no_debugging_features` while all nine flags are on | pass |
| adb remains available under every policy | adb kept working throughout, including the reboot | pass |

## 2026-09-10: inside a live Home Assistant 2026.9.0 (WSL) against the emulator DPC

Driver: `~/workspace/mdm-live/drive_ha.py` over the REST API on a fresh config
directory with the integration symlinked in; HA reached the DPC through
`adb -a` on the Windows host and the DPC reached HA at the WSL address.

| Check | How | Result |
| --- | --- | --- |
| Config flow | `POST /api/config/config_entries/flow` with host, port, token | pass, entry created, 33 entities |
| Webhook registration | DPC report arrives at `/api/webhook/<id>` from the emulator | pass |
| Acceptance round trip | `input_boolean` on, automation calls the camera switch, DPC applies, report received, `camera_disabled_enforced` on and `last_report` advanced | pass, 108 ms |
| Switch attributes | `enforcement: applied`, `reported_value: true`, `policy_version` advanced | pass |
| Off path | helper off, switch and enforced sensor off, problem sensor off | pass |
| Kiosk without packages | switch call raises `HomeAssistantError`, nothing sent | pass |
| Kiosk with packages | text entity set, switch on, `kiosk lock` sensor locked within 1 s; switch off releases within 1 s | pass, after the settled-report fix below |
| Poll fallback | coordinator refresh at 60 s logged success | pass |

Found and fixed during this pass: the DPC answered the policy PUT and sent its
report before lock task mode had engaged, so the `kiosk lock` sensor in Home
Assistant stayed unlocked until the five-minute heartbeat. `KioskActivity` now
asks the service for a report 750 ms after `startLockTask` or `stopLockTask`.

## 2026-09-10: OS update policy, stay awake, kiosk as HOME, reauth (live HA, emulator)

| Check | How | Result |
| --- | --- | --- |
| Reauth after token rotation | DPC token changed; HA raised the reauth flow; completed over the API; entry loaded | pass |
| `auto_os_updates` switch | `dumpsys device_policy` shows `SystemUpdatePolicy (type: 1)`; `system_update.policy` 1 in status; enforced sensor on | pass |
| `stay_awake_on_power` switch | `settings get global stay_on_while_plugged_in` is 7 | pass |
| OS and app version sensors | Android version 15, security patch 2024-09-05, kiosk app version from `installed` | pass |
| Kiosk as HOME | with kiosk on, `resolve-activity HOME` is `KioskHome`; with kiosk off it is the launcher again | pass |
| Reboot into kiosk | kiosk on, `adb reboot`, no push from HA: `lock_task_active` true after boot and HA received the boot report | pass |

## 2026-09-11: Companion installed and run in kiosk through the HA action (live HA, emulator)

| Check | How | Result |
| --- | --- | --- |
| `local_mdm.install_package` | Companion 2026.6.5 `app-full-release.apk` from GitHub with the published digest; `last_install` went `downloading`, `installing`, `installed` | pass, 20 s from action to installed |
| Install result attributes | `package` io.homeassistant.companion.android, `message` INSTALL_SUCCEEDED | pass |
| Kiosk app version sensor | `2026.6.5-full` after the package-visibility fix | pass |
| Kiosk with Companion as the target | `topResumedActivity` is Companion's LaunchActivity, `lock_task_active` true, screenshot shows Companion's onboarding | pass |
| Bad URL scheme | `ftp://` returns 400 from the DPC and `vol.Invalid` from the action schema | pass |

Found and fixed during this pass: without a `<queries>` element the DPC on
Android 11 and newer could neither read another package's version nor obtain
its launch intent, so the version sensor read unknown and kiosk engaged
around whatever task was already on screen.

## 2026-09-11: Samsung Galaxy Tab A11+ (SM-X230), Android 16, One UI, as a plain app

The tablet still carried its accounts, so Device Owner could not be set;
this pass covers what the DPC does before provisioning.

| Check | How | Result |
| --- | --- | --- |
| Foreground service and endpoint on Android 16 (SDK 36) | `dumpsys activity services` lists MdmService; `/v1/status` answers with os, battery, network | pass |
| Status reports the tablet correctly | model SM-X230, release 16, security patch 2026-05-05, Wi-Fi connected, battery 79 percent charging | pass |
| Bad token | 401 | pass |
| Forbidden key refused before any policy work | `no_config_wifi` gives 422 with the guard's message | pass |
| Policy and install refused when not Device Owner | both 422 "not device owner" | pass |
| Knox state before provisioning | warranty bit 0, verified boot green (the DPC needs neither root nor an unlocked bootloader) | pass |

## 2026-09-11: Samsung Galaxy Tab A11+ (SM-X230), Android 16, as Device Owner

Provisioned after a Settings-driven factory reset with every account step
skipped and Wi-Fi off during setup (`dpm set-device-owner` succeeded on the
first try; Knox warranty bit stayed 0). Paired with the test Home Assistant
over USB (adb forward and reverse), later driven over the LAN.

| Check | How | Result |
| --- | --- | --- |
| Device Owner set on Samsung One UI | `dpm set-device-owner`, status `is_device_owner` true | pass |
| Every non-kiosk flag, both new flags | direct PUT: 12 keys applied, zero failures; `SystemUpdatePolicy (type: 1)`, stay-on 7, `no_install_apps` and the rest in `dumpsys user` | pass |
| Wi-Fi never restricted, adb alive | no `no_config_wifi` restriction; adb answered throughout the policy pass | pass |
| Lock screen action | panel dozed | pass |
| Config flow and 42 entities in live HA | pair over USB forward | pass |
| Acceptance round trip on hardware | camera switch, DPC apply, report, enforced sensor | pass, 114 ms |
| Kiosk with Settings as the target | `KioskHome` is HOME, `lock_task_active` true | pass |
| Reboot into kiosk | `adb reboot` and later the DPC's own reboot action; back in lock task on its own, Wi-Fi reconnected | pass, about 45 s |
| DPC self-update through `install_package` | APK served from the workstation, digest checked, service kept running | pass, 4 s |
| `configure_wifi` endpoint | throwaway network accepted (200); empty SSID refused | pass, with the finding below |
| SSID reporting | null until the DPC enabled location for itself; then the SSID | pass |
| Reboot action | `POST /v1/actions/reboot` | pass |

Found and fixed during this pass:

- Lock task hid the "Allow USB debugging?" dialog, because it belongs to
  `com.android.shell`, which was not in the allow list. With the adb key not
  yet persisted and Wi-Fi off, the tablet was unreachable until the owner
  joined Wi-Fi from the Settings kiosk. The shell package is now always in
  the lock task allow list. Persist the adb key ("Always allow from this
  computer") before the first kiosk.
- `enableNetwork(id, disableOthers = true)` dropped the current connection to
  try the new network and took the tablet off the LAN for a few seconds.
  Provisioning now adds the network without forcing a switch.
- The connected SSID needs the device location toggle, not only the
  permission; the DPC enables both for itself at service start.

Not yet observed: the adb dialog appearing inside kiosk with the shell fix
(the key had not been persisted when it was needed), a real pending OS
update, Android 14, a Companion update over an existing install, and
`configure_wifi` with the real network credentials (only the owner holds
them; run it from the Home Assistant UI).

## Lock splash (2026-09-11, SM-X230)

Debug build installed over adb; kiosk switch cycled off/on from Home Assistant. The DPC's `KioskActivity` drew the chained shield, "MDM MANAGED" and the indeterminate bar full-screen, then Companion resumed as the top activity after the 2 s hold. Screenshot taken 1.2 s after the switch call.

## Reboot response and policy drift (2026-09-11, SM-X230)

With the reboot route answering before `dpm.reboot`, the Home Assistant reboot button returned 200 and the tablet restarted into kiosk (HOME = KioskHome, Companion on top). The coordinator now re-pushes the desired policy when a status report or poll disagrees with it, at most once per 30 s; covered by `test_drifted_report_is_repushed`.

## Lite tier on a Fire HD 8 Plus (2026-09-11, KFONWI, Fire OS 7.3.2.9, Android 9)

Provisioned with `scripts/provision_lite.sh` steps by hand (set-active-admin,
WRITE_SECURE_SETTINGS grant, lock_to_app_enabled, GET_USAGE_STATS and
SYSTEM_ALERT_WINDOW app ops). Over `adb forward`:

- `/v1/status` reports `tier: admin`, `is_device_owner: false`.
- `PUT /v1/policy` with kiosk on (target com.amazon.kindle as a stand-in),
  camera, stay-awake, status bar: kiosk `limited`, camera `applied`,
  stay-awake `applied` (global setting read back as 7), Wi-Fi `applied`,
  status bar and the rest `unsupported`.
- Launcher brought to the front by `am start`: HomeWatch logged the redirect
  and Kindle was resumed within 2 s. Kiosk off: launcher stays; stay-awake
  read back as 0.
- `lock_screen` 200; `reboot` 422 "not device owner".
- Accessibility route tried first and abandoned: Fire OS delivered
  systemui window events to the service but never the launcher's, even
  with typeWindowsChanged and interactive-window retrieval.
- Home Assistant test `test_lite_tier_limits_are_not_failures` covers the
  tier sensors.
- Live on Home Assistant with Local MDM v2026.09.11.4 (Fire on Wi-Fi,
  192.168.30.69): `install_package` with the Companion 2026.6.5 minimal
  APK (after PR #27) showed the platform dialog, `last_install` went
  `awaiting_user` then `installed`, package
  io.homeassistant.companion.android.minimal (the `.minimal` suffix matters
  for `kiosk_packages`). Config flow created the entry; `management_tier`
  = admin, `policies_limited_by_tier` = 10 (kiosk_mode limited, nine
  unsupported), `enforcement_failures` = 0, stay-awake enforced. Starting
  com.amazon.firelauncher/.Launcher by component logged the HomeWatch
  redirect and Companion was back in front within a second. The generic
  HOME intent on an unregistered Fire resolves to Amazon's OOBE activity,
  which adb cannot start (MANAGE_USERS). Open: a `switch.turn_on` naming two
  switches in one call only applied the first; the second took on a single
  call. Not reproduced yet.


## App allowlist and account locks on a Pixel Tablet (2026-09-11, tangorpro, Android 16, patch 2026-05-05)

Provisioned as Device Owner over adb after the supervised child user and
the Google account were removed by hand (`set-device-owner` names each
blocker in turn: "already several users", then "already some accounts").
Paired through the config flow; `management_tier` owner.

- `PUT /v1/policy` with `app_mode: allowlist`, three allowed packages
  (Companion, YouTube Kids, Calculator), `accounts_locked`,
  `add_user_blocked`: YouTube Music and Firefox `suspended=true`, YouTube Kids
  and Calculator not, Settings and the Pixel launcher untouched,
  `no_modify_accounts` and `no_add_user` in the effective restrictions.
- First attempt reported `app_mode: failed`: Android refused to suspend the
  Play Store (`com.android.vending`, installer of record). Play is now on the
  never-suspend list and any other refusal reports `limited` with the
  packages in `unsuspendable`; the re-push reported `applied` with an empty
  list.
- `app_mode: open` lifted both suspensions.
- The same build on the Samsung (SM-X230) kept lock task and Device Owner;
  the old integration's pushes carry no new keys and the DPC defaults them.
- Before the first policy push a fresh entry shows one enforcement failure
  and eleven tier-limited keys from the empty enforcement map; both clear on
  the first push (cosmetic, in the backlog).
- Post-install approval (same day): with the allowlist on, `adb install` of
  a launchable APK produced "New package ... held for approval" in the log,
  `suspended=true` and the package in `pending_packages` within 4 s. Adding it
  to `allowed_packages` unsuspended it and emptied the list; `adb uninstall`
  emptied the list too.
- MAC: `WifiInfo.getMacAddress` returned 02:00:00:00:00:00 on both the legacy
  and the transport-info path for the Device Owner on Android 16;
  `getWifiMacAddress` (factory) works. The UniFi tracker for the same IP
  carries the randomised MAC in use (02:9e:10:35:de:56), which is what the
  integration now links on.
