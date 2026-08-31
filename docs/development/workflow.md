# Synapse Development Workflow

This document defines the required verification sequence for any change that affects the user interface.

## UI Change Validation Sequence

When a change affects the frontend or any desktop-visible UI surface, validate in this order:

1. Backend tests, when backend code changed.
2. `ruff` on the backend files that changed.
3. Frontend tests.
4. `npm run lint`.
5. `npm run build`.
6. Desktop release build:
   - `desktop/scripts/build-release-prototype.ps1`
7. Manual validation of the Tauri executable.

The desktop validation step is mandatory for any UI change. A change is not considered complete until the packaged executable reflects the approved frontend state.

## What to Verify in the Desktop Build

- The executable uses the newest frontend bundle.
- `Settings > About` shows the current `Frontend build` marker.
- The UI rendered by the desktop build matches the browser-validated UI.
- No stale bundle, cache, or release artifact is being reused.

## Troubleshooting Order

If the desktop UI does not match the browser UI, check in this order:

1. `frontend/dist`
2. `desktop/src-tauri/target/release`
3. `desktop/release`
4. Launcher and release manifest paths
5. `AppData` cache/state

## Required Evidence in Final Reports

For UI work, the final report should include:

- Backend test results, if applicable
- Frontend test results
- `lint` result
- `build` result
- Desktop release build result
- Timestamp or version evidence for the packaged executable
- Manual desktop confirmation, when possible
