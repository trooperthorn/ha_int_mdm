# Backlog

- 2026-09-10: compile and run the Android app on a Samsung tablet; fill in
  `live_qualification.md`. Unverified today: foreground service type
  `specialUse` on Android 14 and 15, `KioskActivity` hand-off to the target
  package, `BatteryManager.isCharging` on Samsung firmware.
- 2026-09-10: Android CI job (Gradle wrapper, `assembleDebug`, `lint`) so the
  DPC at least compiles on every PR.
- 2026-09-10: Zeroconf announcement from the DPC and a discovery step in the
  config flow.
- 2026-09-10: reconfigure step for host and port changes.
- 2026-09-10: repair issue when the DPC reports `is_device_owner: false`.
- 2026-09-10: TLS on the DPC endpoint with a pinned self-signed certificate
  entered at pairing time.
- 2026-09-10: `PARALLEL_UPDATES` on the platforms; `exception-translations`;
  brand images; decide whether the ten enforced sensors default to disabled.
- 2026-09-10: additional policies once the base set is qualified: screen
  timeout, `setKeyguardDisabled`, `setPermittedInputMethods`, per-app
  suspension.
