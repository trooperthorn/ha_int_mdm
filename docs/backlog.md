# Backlog

- 2026-09-11: confirm the adb dialog appears inside kiosk with the shell
  allow-list fix (needs a tablet with a revoked adb key and kiosk on).
- 2026-09-11: qualify on Android 14.
- 2026-09-10: Zeroconf announcement from the DPC and a discovery step in the
  config flow.
- 2026-09-10: reconfigure step for host and port changes.
- 2026-09-10: repair issue when the DPC reports `is_device_owner: false`.
- 2026-09-10: TLS on the DPC endpoint with a pinned self-signed certificate
  entered at pairing time.
- 2026-09-10: `PARALLEL_UPDATES` on the platforms; `exception-translations`;
  decide whether the ten enforced sensors default to disabled.
- 2026-09-10: additional policies once the base set is qualified: screen
  timeout, `setKeyguardDisabled`, `setPermittedInputMethods`, per-app
  suspension.
- 2026-09-10: signed release APK as a release asset (needs a signing key
  held outside the repository).
- 2026-09-11: Samsung's FOTA agent does not report through
  `getPendingSystemUpdate` (a real Tab A11+ update went from build
  X230XXU4BZE8 to X230XXS5BZF2 with `pending: false` throughout). Consider
  reading the updater's posted notification or Samsung's Knox update API to
  surface "update available" on One UI.

- Kiosk lock splash: done 2026-09-11 (`KioskActivity` shows the chained shield and MDM MANAGED for 2 s before launching the kiosk package, at boot and on re-assert). Boot-logo background in docs/knox-sdk-assessment.md.
- Done 2026-09-11 (reboot route answers first, delayed reboot): reboot route answered after the reboot started: `POST /v1/actions/reboot` calls `dpm.reboot` before NanoHTTPD writes the response, so Home Assistant's button press gets a 500 even though the tablet restarts. Write `{ok:true}`, then reboot from a 500 ms delayed handler.
- Fire OS 7 (Android 9, API 28) support: guards added 2026-09-11; closed 2026-09-11: Device Owner impossible on Fire OS 7 (protected profile owner in the image, docs/fire-os-assessment.md). Lite tier (device admin + HomeWatch + screen pinning) added the same day; see docs/protocol.md "Lite tier". `Wifi.kt` used `addNetworkPrivileged` (API 31) and `setLocationEnabled` (API 30) without version guards; add the legacy `WifiManager.addNetwork` path and guard the location call before qualifying a Fire HD 8 Plus (2020) as Device Owner.
- Android TV (Sony Bravia, Google TV) tier: feasible via adb Device Owner at the cost of the Google account; needs LEANBACK_LAUNCHER alias, touchscreen/leanback feature flags, D-pad focus. Not started; see docs/android-tv-assessment.md.

- Pixel Tablet profile-based management: app_mode/allowed_packages/accounts_locked keys, allowlist and multi-app lock task modes, HA security_profile select and apply_profile action; options and order of work in docs/pixel-tablet-profiles.md. Not started.
- Lite tier self-update leaves `last_install` at `awaiting_user`: when the DPC updates itself through `install_package`, the platform kills the process before InstallReceiver's STATUS_SUCCESS arrives, so the stored state never reaches `installed` (Fire, 2026-09-11; other packages are unaffected). On service start, if `last_install` is `awaiting_user` and the DPC's own version changed, record `installed`.
- `switch.turn_on` with two Local MDM switches in one call applied only the first (Fire, 2026-09-11, kiosk_mode took, stay_awake_on_power did not; a second single call took). Likely the second PUT raced the first while the coordinator refreshed. Reproduce on the emulator and serialise policy writes per device if confirmed.
- Fresh entry before the first policy push reports 1 enforcement failure and 11 tier-limited keys from the DPC's empty enforcement map (Pixel, 2026-09-11); treat an empty map as `pending` for every key.
- `lock_task_multi` app mode with the DPC grid launcher, `notifications_in_kiosk`, `settings_in_kiosk`: docs/pixel-tablet-profiles.md, not started.
- Attach the DPC APK to each GitHub release from CI: releases are immutable, so `gh release upload` after the fact is refused (2026-09-12). Needs the fleet's signing key in CI (the debug keystore as a repository secret, or a proper release keystore plus a one-time re-enrolment of the three tablets, since a Device Owner cannot change signing key in place).
- `install_apps_blocked` also blocks the DPC's own `install_package` on Android 17 (Pixel, 2026-09-12: "User restriction prevents installing"); document and consider lifting the restriction around a DPC-initiated install.
