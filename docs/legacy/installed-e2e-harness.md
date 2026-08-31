# Installed E2E Harness (Retired)

Status: historical, retired in the v0.01 cleanup campaign.

The former installed E2E harness lived in the Electron main process and drove the
renderer by evaluating JavaScript through `webContents.executeJavaScript`. It
recorded stage receipts under the app runtime directory and captured screenshots
through dedicated preload IPC channels.

The harness was useful while stabilizing the first packaged desktop flow, but it
became a source of false authority for visual validation. Activity, themes and
conversation behavior must now be validated through the real local runtime and
normal component/integration tests, not by injecting renderer scripts from the
main process.

Removed active mechanisms:

- `runInstalledE2E` in Electron main.
- E2E stage, screenshot and audio-fixture IPC channels.
- Window-control smoke based on renderer JavaScript injection.
- Installed E2E receipt paths as active release gates.

Historical evidence remains in prior validation/audit documents and Git history.
Do not restore this harness as a workaround for runtime or visual validation.
