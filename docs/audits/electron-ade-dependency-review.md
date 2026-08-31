# Electron ADE dependency review

> Historical/superseded: the Electron ADE implementation and release artifacts were removed under ADR 0119 on 2026-08-21. This file is retained as historical evidence only, not active frontend architecture.

Reviewed and pinned on 2026-08-20:

- Electron 43.4.0 — MIT, official `electron/electron` repository;
- TypeScript 7.0.2 — Apache-2.0, official `microsoft/TypeScript` repository;
- Dockview 8.2.0 — MIT, official `dockview/dockview` repository;
- Pixi.js 8.20.0 — MIT, official `pixijs/pixijs` repository;
- esbuild 0.28.2 — MIT, official `evanw/esbuild` repository;
- electron-builder 26.15.3 — MIT, official `electron-userland/electron-builder` repository.

Exact versions and registry integrity hashes are locked in `package-lock.json`. The final
`npm audit` reported zero vulnerabilities. Installation emitted deprecation warnings in
transitive electron-builder tooling (`inflight`, old `rimraf`, old `glob`, `boolean`); none
is imported by the packaged renderer. This remains supply-chain maintenance debt, not a
suppressed vulnerability finding.

TypeScript 7's DOM WebGPU declarations overlap Pixi's transitive `@webgpu/types` and
Dockview declarations conflict with `exactOptionalPropertyTypes`. The renderer alone uses
`skipLibCheck` and disables that optional-property mode to isolate upstream declaration
incompatibilities; application source remains strict and is fully type-checked.
