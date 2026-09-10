# Backlog

- 2026-09-10: qualify on a Samsung tablet and Android 14; the emulator pass
  in `live_qualification.md` covers Android 15 only.
- 2026-09-10: `POST /v1/actions/install_package` and the matching Home
  Assistant action. `Installer.kt` and `InstallReceiver.kt` (silent
  PackageInstaller session as Device Owner, optional sha256, signature
  continuity enforced by Android) are in the tree and constructed by the
  service, but the HTTP route and the HA action are not wired: that edit was
  held for an explicit owner decision because it lets the control plane
  install arbitrary APKs on the tablet. Once wired, an automation on the
  github integration's latest release can push
  `https://github.com/home-assistant/android/releases/download/<tag>/app-full-release.apk`
  with the asset digest the GitHub API publishes.
- 2026-09-10: qualify kiosk with the Companion app as the target package on
  hardware; the emulator used Settings as a stand-in.
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
