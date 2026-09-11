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
