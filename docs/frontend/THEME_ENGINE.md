# Theme Engine

Status: **IMPLEMENTED — one bundled default presentation pack**, 2026-10-21.

The engine owns presentation only. It does not change conversation routing,
agent identity, model selection, Swarm execution or backend readiness.

## Ownership and integration

- `apps/frontend-v2/src/shared/themeEngine.ts` owns versioned `ThemePack` data,
  lookup/fallback, CSS token projection and motion policy.
- `settingsPreferences.ts` preserves the existing preference key and IDs. Unknown
  IDs fall back to Synapse Core. Preview applies immediately; Save persists.
- `themeAssets.ts` resolves the pack's bundled icon family. Assets remain local;
  theme data cannot execute scripts or load arbitrary remote assets.
- `main.tsx` applies the pack and the effective system/user motion preference to
  the document root. Settings choices and descriptions come from the same registry.
- `renderer/themeEngine.css` renders bounded background effects and applies pack
  typography, shape, colors and glow to shell, composer and Workspace terminals.
- `Presence.tsx` consumes the pack's palette, presentation style and motion speed.
  Speech amplitude remains measured application data.

## Pack contract

Each pack declares version and stable ID, name/description, semantic colors,
UI/code fonts, panel/control radii, glow intensity, icon family, background
pattern/duration, Presence style/speed and six Swarm identity accents.

### Synapse Core

`synapse` is the only active pack. It establishes the product's default technical
language with bundled local assets:

- a petrol/navy tactical surface with readable off-white typography;
- cyan-white energy for identity and interaction, plus restrained amber signals
  for active, waiting and operational attention states;
- a bundled laboratory video rendered without a color filter or blend mode;
- asymmetric technical corners and illuminated rails in the top bar, navigation,
  composer, conversation edge and Workspace terminals;
- a dedicated `jarvis` Presence renderer built as a non-circular neural lattice
  whose routes and light intensity respond to the measured audio amplitude;
- a Core Swarm sequence whose primary window uses the product cyan and whose
  temporary agents retain distinct, accessible accents.

This direction is inspired by fictional command-center interfaces but uses original
geometry, tokens and motion. It does not bundle third-party logos or visual assets.

### Retired themes

The active registry contains only `synapse`. Cyberpunk and other former packs are no
longer exposed in Settings or accepted as active preferences. Saved preferences that
reference retired IDs are normalized to Synapse Core through the normal resolver.

Future themes should extend this registry with bundled artwork/icons and deliberately
implemented renderer styles as needed. Adding a new visual primitive requires a
renderer implementation and performance verification; it is not arbitrary theme code.
This foundation does not include a theme marketplace, user-imported themes, downloads,
font installation or a generic animation/plugin runtime.

## Motion and resource bounds

Backgrounds use bounded local CSS/canvas layers and pause when focus is lost.
Reduced motion disables decorative CSS animation and transitions, including the
system preference.

Presence caps scheduling at 30 FPS focused, 12 with reduced motion, and 8 unfocused.
Hidden documents stop scheduling; visibility recovery resumes the existing canvas.
Reduced/unfocused modes freeze decorative movement while retaining factual speech
amplitude updates. Canvas resolution remains capped at 2x device pixel ratio.
Timers, animation frames, visibility listeners and resize observers are cleaned up.
No computed-style read is performed each frame to discover the current palette.

Settings and Conversation Log retain their intentionally quiet surfaces. Some
legacy component colors remain outside the pack contract; the engine does not claim
that every existing control has already received individual art direction.

## Verification

- Frontend tests include pack fallback, complete token reset,
  text/muted/accent contrast >= 4.5 against panel colors, icon resolution and motion).
- ESLint and focused strict TypeScript check passed for the engine, preferences,
  assets, Presence and engine tests. Production build and the governed Electron
  application smoke passed in the recorded implementation run.
- `tests/themeEngine.electron.cjs` builds an isolated harness using the real Settings,
  Presence and Workspace components. It verifies both active packs, the active/pause
  animation contract, reduced motion, Settings save without backend, reload restoration,
  and two simulated Swarm windows with themed surfaces. No real agents execute.
- Screenshots are generated under `artifacts/reports/theme-engine/`; the canonical
  Core views are `synapse-core-presence.png` and `synapse-core-workspace.png`, with
  `cyberpunk-presence.png` covering the second complete pack.
- Full renderer TypeScript check remains blocked by Workspace integration errors
  outside this change: missing Frame props in bootstrap screens, tools result typing,
  `ProviderModelOption.name` and `ConversationRecord.updated_at`. The root tsconfig
  also requires explicit Node types for tests; the check with Node/Vite types exposes
  those Workspace errors. This is not a global typecheck success claim.
- No backend change; no Python regression or sidecar rebuild is required.

Run from `apps/frontend-v2`:

```powershell
npm test
npm run lint
npm run build
.\node_modules\.bin\electron.cmd tests/themeEngine.electron.cjs
```
