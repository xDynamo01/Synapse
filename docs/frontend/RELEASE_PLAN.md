# Frontend V2 Windows Release Plan

Status: **FRONTEND V2 RELEASE CANDIDATE READY**

This is the canonical plan for the Frontend V2 Windows release candidate campaign.
The plan governs only packaging and release readiness. It does not authorize new
product capabilities, product redesign, remote upload, advanced panels, or a
second backend.

## Release readiness rule

The campaign can end as `FRONTEND V2 RELEASE CANDIDATE READY` only when the
installed Windows product is validated with evidence:

- Frontend source/build tracking is coherent.
- Electron starts, supervises and shuts down the packaged backend sidecar.
- Normal release startup does not depend on a developer terminal, repository
  checkout, global Node, global Python or an external backend.
- Windows installer exists and is smoke-tested.
- Clean install, first-run, restore, conversation, Voice, Presence, Activity,
  Insight, Settings, Notifications, attachments, window controls, shutdown and
  uninstall are validated.
- User-data preservation policy is explicit.
- Package hygiene, checksums, manifest, release notes, signing status and gates
  are recorded.
- No known release blocker remains.

All required v0.01 gates listed here are green. Provider-level limitations and
unsigned binaries are recorded as non-blocking release notes.

Regression correction campaign: the former installed E2E harness based on
Electron main-process renderer injection has been retired. Current validation
uses normal frontend/backend tests plus direct local runtime observation for
visual Activity, Settings, theme and conversation behavior. Historical context is
kept in `docs/legacy/installed-e2e-harness.md`.

## Slice 15.1 — Release source/worktree normalization

Status: **READY**

Objective: classify and normalize everything required for a reproducible release.

Scope:

- `apps/frontend-v2`
- backend sidecar source and build script
- scripts needed for packaging/release
- official assets
- frontend release docs
- generated outputs
- root `Synapse.exe` developer launcher

Classification vocabulary:

- `SOURCE`: required to reproduce the release and must not be accidentally ignored.
- `GENERATED`: derived build output that must be reproducible.
- `ARTIFACT`: produced deliverable or developer convenience binary.
- `IGNORE`: disposable local output that should stay ignored.
- `UNEXPECTED`: item whose role is not governed by this campaign.

Acceptance criteria:

- Required source is not ignored by Git.
- Generated outputs are not confused with source.
- Release artifacts are separated from source.
- `.gitignore` reflects generated/local outputs only.
- No commit, push or staging is required to continue.

Evidence:

- `git check-ignore` confirmed required release source is not ignored:
  `apps/frontend-v2/package.json`, `apps/frontend-v2/package-lock.json`,
  `apps/frontend-v2/src/main/main.ts`, official icon assets,
  `backend/synapse/sidecar.py`, `scripts/build_backend_sidecar.ps1` and this
  release plan are not ignored.
- Generated/local outputs remain ignored: `apps/frontend-v2/dist/`,
  `apps/frontend-v2/node_modules/` and `backend/dist/`.
- `apps/frontend-v2/release/` is reserved for release artifacts.

Blockers: None for this slice. Source remains untracked in the current worktree,
but it is not accidentally ignored and no stage/commit is required by this plan.

Next step: Audit current worktree classification and adjust ignore rules if necessary.

## Slice 15.2 — Packaged backend sidecar supervision

Status: **READY**

Objective: Electron starts, supervises and shuts down the packaged backend sidecar.

Expected flow:

```text
Synapse starts
→ Electron resolves packaged sidecar
→ starts synapse_backend
→ obtains actual loopback endpoint
→ waits for readiness/handshake
→ frontend connects
→ Electron supervises lifecycle
→ Synapse closes
→ sidecar shuts down cleanly
```

Acceptance criteria:

- Release startup does not normally fall back to `http://127.0.0.1:8717`.
- Explicit development override remains possible through a backend URL override.
- Dynamic sidecar port is supported.
- Readiness timeout is explicit and frontend-safe.
- Sidecar crash is visible as degraded/error state.
- Shutdown terminates the owned sidecar.
- Repeated startup does not collide with another instance.
- No second backend is introduced.

Evidence:

- Electron main process now uses `BackendSidecarSupervisor`.
- Normal startup resolves the packaged sidecar from
  `process.resourcesPath/synapse-backend/synapse_backend.exe`.
- Development overrides remain explicit through `SYNAPSE_BACKEND_URL` and
  `SYNAPSE_BACKEND_SIDECAR_PATH`.
- Sidecar uses dynamic loopback port and existing
  `runtime/backend-handshake.json` readiness contract.
- `npm run test:electron-smoke` passed with sidecar supervision active.
- Installed smoke passed with `new_sidecar_processes_after_close=0`.

Blockers: None for this slice.

Next step: Implement Electron main-process sidecar lifecycle using the existing handshake.

## Slice 15.3 — Windows packaging / installer

Status: **READY**

Objective: add governed Windows packaging that produces a distributable installer.

Acceptance criteria:

- `apps/frontend-v2/release/` is produced.
- Installer `.exe` is produced.
- Package includes Electron app, renderer build, preload/main, official assets,
  backend sidecar and required runtime files.
- Package does not require global Node, global Python, source checkout or
  developer terminal.
- Official icon is used for app window and package metadata where supported.
- Tooling is recorded in `package.json`/lockfile and is reproducible.

Evidence:

- Added `electron-builder@26.15.3` as governed packaging tooling.
- `npm run package:win` produced
  `apps/frontend-v2/release/Synapse-Setup-v0.01.exe`.
- Package includes `resources/synapse-backend/synapse_backend.exe`.
- `app.asar` hygiene scan found no `.git`, `.env`, `src/`, `tests/`,
  `node_modules/` or sourcemaps.
- Package uses the official `assets/icons/synapse.ico`.

Blockers: None for package generation.

Next step: Add minimal mature Electron packaging tooling and package configuration.

## Slice 15.4 — Installed product validation

Status: **READY**

Objective: validate the installed product, not only the repository launcher or
unpacked output.

Acceptance criteria:

- Install succeeds.
- Installed app launches without checkout/runtime globals.
- Packaged sidecar starts and becomes ready.
- First-run and existing-user restore paths are exercised as far as governed
  local providers allow.
- Text conversation, Voice, Presence, Activity, Insight, Settings,
  Notifications, attachments and window controls are smoke-tested.
- Close/restart is clean.
- Uninstall succeeds.
- User-data preservation policy is observed.
- No owned sidecar process remains orphaned.

Evidence:

- Silent install to an explicit temporary directory passed with `install_exit=0`.
- Installed app E2E passed for first launch with `first_launch_exit=0`.
- Installed app E2E passed for restart/restore with `restart_restore_exit=0`.
- Installed package contained both `Synapse.exe` and
  `resources/synapse-backend/synapse_backend.exe`.
- Shutdown left `new_sidecar_processes_after_close=0`.
- Silent uninstall passed with `uninstall_exit=0` and removed the install
  directory.
- Packaged backend clean-data API validation passed health, bootstrap,
  first-agent creation, conversation open and history retrieval.

Installed Voice/STT/TTS evidence is now green; see Slice 15.7 and the packaged
voice smoke artifact.

Regression work: supervisor diagnostics now persist sanitized lifecycle/stdout/
stderr facts under the app user-data runtime directory. The previous injected
installed E2E harness is retired and no longer part of current release gates.

Resolved during continuation:

- The installed E2E runner previously accepted the Conversation Log while
  onboarding was still active; the rail controls in that state are intentionally
  inert. The runner now waits for the real workspace main area before clicking
  Activity.
- The failure receipt previously bypassed the serialized receipt writer and
  could erase earlier stages. Failed stages now go through the same receipt path.
- First-run now persists the explicitly selected LM Studio provider/model through
  backend Provider Settings before creating the Primary Agent.
- Model Router now preserves an agent's explicit `preferred_model` instead of
  replacing it with an automatic resource recommendation.
- Packaged clean-data text conversation now reaches `generation_completed` and
  persists completed user/assistant history.
- Current runtime validation must prove the real composer path directly:
  submit handler, frontend request, backend turn, assistant response, persisted
  user/assistant history, one user bubble and one assistant bubble in the
  Conversation Log, plus attachment staging, manual STT, Conversation Mode,
  TTS, shutdown and sidecar cleanup; restart/restore receipt is also green.

Installed installer smoke and lifecycle checks are complete. The latest clean
install receipt pair (first launch and restart/restore) is green; the artifact
checksum is recorded in `release/checksums.txt` and `release-manifest.json`.
Visual media is canonicalized under `apps/frontend-v2/assets/media/`; the
provided navigation and notification icon sources are preserved there.
Activity without a selected project is represented as a healthy empty/idle
scope rather than `activity unavailable`.

## Slice 15.5 — Release artifacts

Status: **READY**

Objective: produce final release artifacts.

Expected output:

```text
apps/frontend-v2/release/
├── Synapse-Setup-<version>.exe
├── checksums.txt
├── release-manifest.json
└── release-notes.md
```

Acceptance criteria:

- SHA-256 checksums match final artifacts.
- Manifest includes version, platform, architecture, artifact, SHA-256, signing
  status and relevant runtime metadata.
- Release notes are factual and include known limitations.
- Signing status is `UNSIGNED` if no legitimate certificate is configured.
- No certificate is fabricated.

Evidence:

- `checksums.txt` generated.
- `release-manifest.json` generated.
- `release-notes.md` generated.
- Installer SHA-256 (latest v0.01 rebuild):
  `8D33D99F23E224F5D9E82FB29620D7B3A69DF0C959EF4CD9D47DB66A05FFDC90`.
- Authenticode status is `NotSigned`; manifest records `UNSIGNED`.

Blockers: None for artifact generation.

Next step: Generate final artifact metadata after installer validation.

## Slice 15.6 — Final RC audit

Status: **READY**

Objective: execute a final cross-cutting audit and decide readiness.

Audit terms:

```text
TODO
FIXME
HACK
mock
fake
stub
placeholder
dev-only
localhost hardcode
absolute repo path
debug flag
default Electron icon
untracked source dependency
orphan process
installer dependency on checkout
missing sidecar
missing asset
stale version
```

Acceptance criteria:

- Occurrences are classified as blocker, governed test/development fixture,
  documentation reference or non-blocking debt.
- Blockers are corrected or the final status is `NOT READY`.
- Affected gates are repeated.
- Final status is recorded in this document.

Evidence:

- Final audit found no release blocker in packaged file hygiene.
- Final audit classified backend mock/placeholder occurrences as governed test or
  development fallback paths; they are not shipped runtime paths.
- Clean packaged conversation stream now passes with `generation_completed`.
- Clean packaged Voice transcription and Voice conversation turn pass with the
  packaged Faster-Whisper/Piper runtime and default pack.

Blockers:

Provider-level generation cancellation/full-duplex interruption and Authenticode
signing remain explicit non-blocking limitations.

Next step: Run after slices 15.1 through 15.5 complete.

## Slice 15.7 — Packaged Voice Runtime & Default Voice Pack

Status: **READY**

Objective: make packaged Voice fully functional in a clean install and distribute
an exactly six-voice governed default TTS pack.

Acceptance criteria:

- STT works in a clean install without developer cache.
- TTS uses a real packaged provider/runtime.
- Default Voice Pack contains exactly six redistributable usable voices:
  three masculine and three feminine profiles.
- Each voice has a stable logical `voice_id`, display name, locale, voice
  profile, provider/engine, asset reference, version, SHA-256 checksum and
  license/provenance.
- Backend discovers only voices actually installed and checksum-valid.
- Settings lists voices from the backend and persists the selected logical voice.
- Missing/corrupt assets are explicit and do not silently fall back.
- Packaged paths do not depend on the repository checkout or developer caches.
- Clean installed Voice/STT/TTS and Conversation Mode validation passes.

Evidence from this continuation:

- Added backend Voice Pack discovery boundaries:
  `GET /api/voice/packs` and `GET /api/voice/voices`.
- Added checksum-backed per-voice usability classification:
  `ready`, `missing` and `corrupt`.
- Added logical voice id resolution for Piper model selection; Settings persists
  `default_tts_voice` instead of a filename.
- Settings now loads Voice Packs/voices through the typed frontend client and
  disables incomplete/corrupt voices.
- Focused tests passed:
  `pytest tests/test_voice_runtime.py tests/test_speech_adapters.py -q`
  reported `47 passed`.
- Frontend focused gates passed:
  `npm test` reported `9 passed / 72 tests`, and `npm run build` passed.

Evidence:

- Clean packaged smoke passed with Faster-Whisper tiny STT, Piper synthesis and
  six checksum-verified public-domain voices (3 masculine, 3 feminine).
- Installer smoke, restart, shutdown and uninstall passed with the packaged
  runtime; no developer checkout or global runtime was required.

Limitations: provider-level generation cancellation/full-duplex interruption and
Authenticode signing remain explicit non-blocking limitations.

## Gate ledger

Status: **EXECUTED**

Required gates:

```text
npm test
npm run build
npm run lint
npm run test:electron-smoke
frontend/backend focused tests
architecture tests
ruff
mypy
sidecar smoke
root Synapse.exe smoke
package build
installer smoke
clean-install validation
uninstall validation
git diff --check
```

## Final decision

Status: **FINAL**

Decision: `SYNAPSE v0.01 READY`.

The latest installed receipts prove the full required chain for first launch and
restart/restore:

```text
sidecar ready
→ backend-base-url resolved
→ renderer bootstrap
→ workspace operational
→ Activity interaction
→ Settings interaction
→ controlled shutdown
→ sidecar stopped
```

The installed validation also proved silent install, clean uninstall and
`new_sidecar_processes_after_close=0`. Remaining limitations are explicitly
non-blocking for v0.01: unsigned installer, no auto-update, and provider-level
full-duplex/generation-cancellation limits.
