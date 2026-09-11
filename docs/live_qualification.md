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

Not yet observed: a Samsung tablet, Android 14, a real pending OS update on
hardware, and a Companion update (same package, newer version) rather than a
first install.
