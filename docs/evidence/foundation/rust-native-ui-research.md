# R1 — native Rust feasibility research

Date/access date: 2026-11-09. Status: RESEARCH ONLY; all executable/physical probes NOT RUN. Gate 00 remains BLOCKED. No compiler/crate/binding is selected or accepted by this report. No installation or implementation was performed; only this ignored report was written.

Authority read: `docs/specs/2026-11-06-synapse-0.3-decision-charter.md` (2026-11-09 amendment), particularly PL-001–PL-006; `docs/superpowers/plans/2026-11-09-rust-python-foundation-revalidation.md`, R1. Binding scope: CR-001–004, PX-002–005, VO-001/006, MI-003/004, SE-001–006, PL-001–006, QA-001–003. Voice identity, translation, model execution and memory semantics are not implemented by these probes.

## Candidate comparison

The proposed first comparison is native **egui/eframe versus Xilem/Masonry**. Both provide Rust-authored native presentation without an application webview. iced is a third research comparator with a decisive accessibility uncertainty. This is an engineering recommendation for experiments, not a stack decision.

| Requirement | egui/eframe native | Xilem/Masonry native | iced native comparator |
| --- | --- | --- | --- |
| Transparent Assistant | `ViewportBuilder::with_transparent`, transparent panel and `App::clear_color`; macOS shadow can cause ghosting [E2]. Actual composition, bubble hit testing and focus require proof. | winit supplies a transparency request, which can be only a platform hint [N1]. End-to-end Xilem alpha surface configuration/clear behavior was not established. Fail this early if a supported path cannot be identified. | `window::Settings.transparent` exists; blur differs by OS [I2]. |
| Audio-reactive custom Presence | `Painter` draws shapes/text [E3]. Feed measured Rust audio envelopes; the drawing API itself proves no audio behavior. | Custom widgets expose `paint`, animation, accessible role/node and text-event hooks [X3]. These permit a candidate native Presence path; performance remains unknown. | Canvas provides custom interactive 2D drawing [I3]. |
| Terminal grid and collapsing rail | Native custom layout/painting is feasible in principle; terminal emulation, cell selection, scrollback and rail reflow are separate application work. | Grid, Split, Flex, selectable Prose and TextInput are documented [X2]. Conditional rail removal and actual terminal behavior still need proof. | PaneGrid supports dynamic splits, resizing and active panes [I4]; this is layout, not terminal emulation. |
| Keyboard/IME | Preedit/commit events are documented [E4]. Test native focus, candidate placement, cancellation and Unicode editing. | Widget hooks explicitly cover focus and IME sessions [X3]. Platform behavior is unmeasured. | Upstream IME implementation merged into TextInput/TextEditor [I5]; do not infer regression-free behavior from that merge. |
| Actual accessibility tree | Upstream documents AccessKit integration, built-in widget semantics and explicit metadata for custom drawings [E5]. Inspect the running OS tree and screen-reader actions. | AccessKit is part of the native stack [X1]; custom widgets must describe roles/nodes and handle accessible actions [X3]. Actual OS tree not observed. | Accessibility integration issue #552 remains open [I6]. Do not count visible text, a native window node or keyboard support as widget-tree compliance. |
| Platforms/licence | Upstream lists Windows/Linux/macOS native support; MIT OR Apache-2.0; fonts have separate licences [E1]. All physical lanes NOT RUN. | Native winit/Vello/wgpu/Parley/AccessKit stack, Apache-2.0, experimental [X1]. Release notes call it alpha quality and expect breaking changes [X4]. All physical lanes NOT RUN. | Cross-platform Rust framework, MIT [I1]. Physical lanes NOT RUN; accessibility gap prevents an acceptance assumption. |

Observed documentation versions: egui/eframe 0.37.0, iced 0.14.0, Xilem/Masonry 0.4.0. These identify browsed pages, **not proposed dependency pins**. Xilem main README and v0.4 release advertise different MSRVs (1.96 versus 1.88) [X1, X4]; source/ref identity must be fixed before selecting a compiler. Avoid xilem_web, wasm application targets, generated JS clients and any archived Synapse imports.

Build/packaging unknowns: resolve exact lock/feature graphs, renderer/GPU support, native toolchains, redistribution notices and package startup from clean hosts. Xilem upstream names Linux pkg-config, clang, Wayland, xkbcommon, XCB and Vulkan-loader development dependencies [X1]. egui renderer choice changes its dependency surface. No evidence here establishes software fallback, remote-session graphics, installers, signing or update compatibility. Slint was considered but not shortlisted: upstream describes a separate Slint UI language and multiple licensing routes [S1]; the strict Rust/Python-only requirement should not be silently widened to accept another authored UI language.

## Internal browser without authored JavaScript

A separate native browser adapter is plausible; it must never become the application UI or own Core authority. **Standalone Wry is a candidate browser wrapper, not permission to introduce Tauri.** Its host uses Windows WebView2, macOS WebKit and Linux WebKitGTK [B1]. Native navigation, popup, download and permission callbacks exist [B2]. A Rust broker can consume those callbacks without application-authored scripts. On the inspected Windows upstream path, IPC attachment is conditional and adds a JavaScript shim when enabled [B3]. Therefore omit IPC handlers, initialization scripts, script evaluation, host objects and custom privileged content protocols, and audit the exact selected source on every OS. This is a proposed configuration, not a verified absence of bridges.

Hard gaps:

- Wry raw-window/child embedding is X11-only on Linux; Wayland requires GTK hosting plus event-loop integration [B1, B2]. Both shortlisted UIs use winit: a compatible GTK browser process/window arrangement, focus, scaling and lifecycle remain unresolved. A separate internal native browser window/process is a possible probe, not assumed equivalence to an embedded pane.
- Rendering a remote page does not prove autonomous read/click/submit. Wry's documented callbacks do not by themselves provide a cross-platform semantic browser automation API. Windows exposes native DevTools protocol calls [B5]; investigate bounded DOM/accessibility/input operations without Runtime.evaluate or injected scripts. Equivalent macOS/Linux capability remains UNKNOWN. No cross-platform compliant path means BLOCKED.
- Engine sandbox, profile encryption, credential handles, clipboard/file chooser, subframe redirects, service workers and runtime update policy need R4 threat-model evidence. Microsoft explicitly treats hosted content as insecure and recommends disabling host objects/web messages when unused [B4]. Do not claim that embedding a webview establishes containment.
- Defaults are unsuitable as policy: documented Wry downloads allow by default; persisted browser permissions can bypass the permission callback [B2]. Use fresh synthetic profiles; deny downloads/popups/permissions unless broker-authorized. Browser-profile confidentiality is not established by incognito mode or by OS support claims. Do not access personal accounts in R1.

Wry's wrapper licence is Apache-2.0/MIT [B1]; browser engines, runtime redistribution and update obligations are separate inventory items. WebView2 availability is a deployment prerequisite, WebKit is OS-coupled on macOS, and WebKitGTK adds Linux packages [B1]. The library README and live API documentation can differ in platform age claims; record actual pinned runtime minimums and deny unsupported hosts instead of inheriting marketing support lists.

## Comparable probes and proposed budgets

These numerical budgets are **engineering proposals**, not charter values or measured host limits. Before comparison, record actual OS/build/architecture, CPU/logical cores, RAM, GPU/VRAM/driver, display refresh/DPI, graphics backend and audio device/rate/buffer. Freeze one budget file with that host identity. If a metric cannot be measured, record NOT RUN/BLOCKED; do not adjust a failed threshold after seeing candidate results.

| Metric | Proposed initial threshold and measurement |
| --- | --- |
| First usable native frame | Cold p95 <= 2 s; warm p95 <= 750 ms; 20 launches each; report browser start separately. |
| Native UI memory | Peak private working set/RSS <= 256 MiB for the fixed fixture; report committed memory too. Separate browser-process aggregate ceiling <= 768 MiB for one synthetic page. No AI weights/worker included; later whole-stack budget remains required. |
| Pacing at 60 Hz | 5-minute active fixture: frame interval p95 <= 20 ms, p99 <= 33.3 ms; report dropped frames and longest stall. No animation when window hidden except declared lifecycle work. |
| CPU/GPU | Idle/breathing average CPU <= 5% of one logical core; active <= 30%; report process CPU in core-normalized units. GPU busy delta <= 10 percentage points above desktop baseline; record engine counters/backend and memory. Lack of comparable GPU counters is missing evidence. |
| Reactive signal/interruption | Audio callback timestamp to rendered listening/output-envelope update p95 <= 100 ms; interrupt to visual acknowledgement p95 <= 50 ms and output stop <= 100 ms. Measure the physical playback path separately from callback delivery. |
| Bounded audio/lifecycle | Proposed rolling raw buffer <= 500 ms, RAM-only, overwrite/discard continuously; no raw samples in files/logs/network. Permission denial/device removal must stop stream activity and show failure within 1 s; cancel/shutdown must leave no capture or orphan browser process within 2 s. |

Use identical viewport, fonts, fixtures, renderer class, release profile and host for each candidate. Alternate candidate order; retain per-run values, artifact/lock hashes and command receipts. Suggested sequence:

1. **Early failures:** transparent bubbles over a checkerboard desktop; native focus/IME; running accessibility tree (UIA + Narrator/NVDA on Windows, AX + VoiceOver on macOS, AT-SPI + Orca on Linux). Require role/name/value, focused element, rail expanded/collapsed state, accessible invocation and text selection. Tree inspection is necessary; screen-reader interaction also matters [A1]. No substitutes from internal test trees or screenshots alone.
2. **Same small UI:** one normal terminal and collapsible rail; explicitly enter a synthetic 2x2 agent terminal grid with role/state/action/evidence labels; collapse rail and measure terminal expansion. Use bounded synthetic ANSI/Unicode stream, including combining marks/emoji/CJK. Test keyboard-only navigation, PT-BR dead keys, CJK preedit/commit/cancel, DPI 100/150/200%, resize, clipping and scrollback. Layout demonstration does not prove a PTY implementation.
3. **Real audio:** native microphone input and an app-owned synthetic output stream drive distinct measured envelopes; silence, speech, playback, cancellation and unplug/replug must change Presence correctly. CPAL supplies Rust device and stream callbacks [AU1]; that does not prove system loopback capture, acoustic latency or permission correctness. No wake model/AI required. Capture only aggregate/timestamp evidence, never retained raw audio. A timer-only animation is insufficient.
4. **Lifecycle:** close/reopen with background host explicitly disabled/enabled; tray availability, logout/lock default stop policy, permission deny/revoke, crash and recovery. Window lifetime must not make the UI authoritative. Locked/no-user behavior and actual device release need OS-level observation.
5. **Browser hostile fixtures:** synthetic trusted/untrusted origins, subframes, redirects, popup/download/file/clipboard/mic attempts and fake tool requests; deny after revocation and inspect receipts. Prove read/click/submit without authored/injected JS; inspect process tree, sandbox status, profile boundaries and forbidden local/network effects. Test clean install/offline failure. Repeat Windows, Linux X11, Linux Wayland and macOS lanes explicitly; CI is not physical audio validation.

Decision threshold: no candidate, renderer, browser or source pin is accepted here. egui/eframe is the first probe recommendation because the documented native rendering and accessibility paths are comparatively explicit; Xilem/Masonry provides a meaningfully different retained-tree comparison. Transparency in Xilem, terminal accessibility, physical audio latency, native browser automation and Wayland hosting are decisive unknowns. Missing physical Linux/macOS evidence remains NOT RUN/BLOCKED under PL-004. Produce the superseding ADR only after reproducible probes and independent QA.

## Primary sources

All accessed 2026-11-09. Moving branch/latest pages are research pointers, not immutable build evidence.

- E1: [egui upstream README/platforms/licences](https://github.com/emilk/egui).
- E2: [ViewportBuilder transparency](https://docs.rs/egui/0.37.0/egui/viewport/struct.ViewportBuilder.html).
- E3: [Painter API](https://docs.rs/egui/latest/egui/struct.Painter.html).
- E4: [ImeEvent](https://docs.rs/egui/latest/egui/enum.ImeEvent.html).
- E5: [egui accessibility guidance](https://github.com/emilk/egui/blob/main/docs/accessibility.md).
- X1: [Xilem native stack/build/licence/MSRV](https://github.com/linebender/xilem).
- X2: [Xilem built-in views](https://docs.rs/xilem/latest/xilem/view/index.html).
- X3: [Masonry Widget paint, accessibility and IME](https://docs.rs/masonry_core/latest/masonry_core/core/trait.Widget.html).
- X4: [Xilem release maturity/MSRV](https://github.com/linebender/xilem/releases).
- I1: [iced upstream](https://github.com/iced-rs/iced).
- I2: [iced native window Settings](https://docs.rs/iced/latest/iced/window/struct.Settings.html).
- I3: [iced Canvas](https://docs.rs/iced/latest/iced/widget/canvas/index.html).
- I4: [iced PaneGrid](https://docs.rs/iced/latest/iced/widget/pane_grid/index.html).
- I5: [iced merged IME implementation](https://github.com/iced-rs/iced/pull/2777).
- I6: [iced accessibility integration issue](https://github.com/iced-rs/iced/issues/552).
- N1: [winit transparency contract](https://docs.rs/winit/latest/winit/window/struct.WindowAttributes.html).
- S1: [Slint upstream FAQ: UI language, platforms and licence routes](https://slint.dev/faqs).
- B1: [Wry upstream native hosting, prerequisites and licence](https://github.com/tauri-apps/wry).
- B2: [Wry WebViewBuilder platform/callback limits](https://docs.rs/wry/latest/wry/struct.WebViewBuilder.html).
- B3: [Wry Windows conditional IPC/script path](https://github.com/tauri-apps/wry/blob/dev/src/webview2/mod.rs).
- B4: [Microsoft WebView2 security guidance](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/security).
- B5: [Microsoft native WebView2 interface](https://learn.microsoft.com/en-us/microsoft-edge/webview2/reference/win32/icorewebview2?view=webview2-1.0.3650.58) (page identifies itself as an older reference; verify selected SDK).
- AU1: [CPAL Rust audio streams](https://docs.rs/cpal/latest/cpal/).
- A1: [AccessKit application testing guidance](https://github.com/AccessKit/accesskit/blob/main/README-APPLICATION-DEVELOPERS.md).
