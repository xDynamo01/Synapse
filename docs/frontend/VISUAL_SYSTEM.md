# Synapse Frontend V2 — Visual System

Status: `FRONTEND V2 SLICE 11 NOTIFICATIONS READY`

This document defines visual direction and semantic rules only. It does not implement UI, shaders, canvas scenes, image generation, or frontend dependencies.

## Reference handling

Approved visual references should be preserved under:

```text
artifacts/diagrams/frontend-v2-references/
```

References are direction only. They are not pixel-perfect UI requirements and must not be copied as literal interface layouts.

Canonical Slice 2 structural reference:

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ Synapse                                                    window controls │
├────┬───────────────────────────────────────────────┬─────────────────────┤
│ ◎  │                                               │ Conversation Log    │
│ ◌  │              factual Presence                 │ real conversation   │
│    │        factual status / degraded state         │ stream + history    │
│    │                                               │ minimizable         │
│ ⚙  │             + text/commands  🎙 mode           │                     │
└────┴───────────────────────────────────────────────┴─────────────────────┘
```

This structural shell supersedes earlier layout references that placed the Conversation Log as a bottom band. Earlier references remain historical mood references only.

Historical preserved references:

- `artifacts/diagrams/frontend-v2-references/presence-voice-mode-reference.png`
- `artifacts/diagrams/frontend-v2-references/activity-constellation-reference.png`
- `artifacts/diagrams/frontend-v2-references/synapse-icon-transparent-reference.png`
- `artifacts/diagrams/frontend-v2-references/synapse-icon-dark-reference.png`

## Visual principles

- Futuristic, elegant, ethereal, functional.
- Low visual noise.
- Dark local-first workspace.
- Cyan/teal is the core Synapse energy color.
- Motion communicates factual system state, not decoration alone.
- Organic neural clustering is preferred over rigid org charts.
- Interface density must stay lower than the old ADE direction.

Avoid:

- JARVIS-style overload;
- symmetric spider charts;
- static org charts;
- fake agent activity;
- decorative “AI magic” effects with no operational meaning;
- dense permanent panels.

## Presence

Presence is the default main visual surface. In Slice 7 it is an implemented internal
visualization, not a placeholder and not a Voice Mode screen.

### Form

Presence should use an ambient circular/particle field:

- central energy core;
- soft halo/ring;
- sparse particles;
- subtle connection lines only when meaningful;
- state-specific motion and intensity;
- no dense labels by default.

### State grammar

| State | Visual behavior | Data source |
| --- | --- | --- |
| Idle | slow breathing glow, sparse particles, stable ring. | Primary Agent exists and no active turn/session. |
| Listening | ring opens, waveform-like pulse, input-focused particles. | Voice recording/session facts. |
| Transcribing | narrow inward pulse, text-capture shimmer. | STT/voice processing facts. |
| Thinking/processing | denser inner motion, controlled acceleration. | Conversation stream or agent turn lifecycle. |
| Responding | outward flow from core to Conversation Log. | Streamed assistant response. |
| Speaking | audio-reactive ring, playback pulse. | TTS/synthesis playback state. |
| Waiting for approval | amber accent, slowed motion, visible approval count. | Approval/notification facts. |
| Degraded | dimmed core, warning accent, explicit reason in UI text. | Health/provider/model/voice failures. |
| Unavailable | low-energy static state, recovery action visible. | Backend unavailable or no usable Primary Agent. |

Presence must not infer work from animation. If the backend state is unknown, the visual state is unknown/degraded.

Slice 7 implementation rules:

- Presence represents Synapse as one entity across text, voice, idle and degraded states.
- The main renderer is PixiJS; React owns only the component boundary and application facts.
- Scene state is produced by an adapter from application state and then consumed by the GPU renderer.
- The implemented state set is `idle`, `listening`, `transcribing`, `processing`, `speaking`, `interrupted`, `failed`, and `disconnected`.
- `listening` and `speaking` may react to real audio amplitude; other states must not preserve stale audio amplitude.
- No `VOICE MODE` label, central waveform-first visual, synthetic task progress or decorative HUD is allowed.
- Budget: at most 96 particles in normal mode, 28 in reduced motion, 45 FPS while focused and 12 FPS when the document is hidden.
- Resize keeps the visual centered and proportional inside the workspace without covering the composer or Conversation Log.
- If Pixi/GPU initialization fails, a discreet CSS fallback core keeps the shell usable.
- Accessibility exposes a factual state label such as `Synapse idle`.

## Activity / Constellation

Activity is a selectable visual mode, not the default shell.

### Form

The constellation should feel organic and neural:

- irregular clusters;
- heterogeneous node sizes;
- subtle cross-links;
- particle trails for live events;
- visible but restrained labels;
- no fixed radial symmetry;
- no hierarchical org-chart layout unless the underlying fact is actually hierarchical.

### Semantic grammar

| Element | Meaning |
| --- | --- |
| Central cluster | Current project/workspace activity. |
| Agent node | Real agent/session participating in work. |
| Tool node | Real tool/command execution or pending intent. |
| Approval node | Pending user decision. |
| Conversation node | Conversation or turn reference. |
| Insight node | Hardware/model/provider fact when relevant. |
| Edge | Factual relationship or event causality. |
| Particle pulse | New event from activity stream. |
| Broken/dim edge | Failed, cancelled, unavailable, or resync-required state. |

Slice 8 implementation rules:

- Activity is toggled from the sidebar and replaces only the central visual surface; the composer and Conversation Log remain in place.
- The renderer uses PixiJS and consumes frontend-owned scene state from the operational projection adapter.
- Layout is stable and asymmetric: entity identity hashes determine approximate position so the same entity does not jump on every event.
- Color encodes function/role; runtime status uses motion and halo, not arbitrary color changes.
- Lines are drawn only for factual backend relations.
- Flow particles appear only for bounded live relation events and are removed in reduced motion.
- Large activity sets degrade deterministically: normal mode renders at most 54 nodes, 76 edges and 18 flows; reduced motion renders at most 28 nodes, 40 edges and 0 flows.
- Extra entities are represented by an aggregate node, not by unlimited labels or fake nodes.
- Focused budget is 36 FPS normal / 18 FPS reduced; hidden/unfocused budget is 10 FPS normal / 6 FPS reduced.
- Empty, degraded, resyncing and disconnected states remain explicit and must not be visually filled with fake work.
- If Pixi/GPU initialization fails, a static DOM fallback shows essential factual nodes.

### Color grammar

| Color | Meaning |
| --- | --- |
| Cyan/teal | Synapse core, active stable facts. |
| Blue | research/inspection/information flow. |
| Violet | planning or reasoning activity. |
| Amber | approval required or user decision pending. |
| Orange | backend/tool execution. |
| Yellow | review/verification attention. |
| Red | failure, blocked state, or unsafe action prevented. |
| Gray | unknown, inactive, unavailable, or historical. |

Color is semantic, not decorative. The same condition must use the same visual language across Presence, Activity, notifications, and Conversation Log.

## Conversation Log

The Conversation Log should be persistent and minimizable.

Visual requirements:

- readable first;
- low chrome;
- clear distinction between user text, voice transcript, assistant response, tool/approval notices, errors, and attachments;
- streaming response state must be visible without fake completion;
- voice transcript must show uncertainty when transcription is partial or failed;
- minimized state must preserve important activity indicators.

In Slice 2 it is an elevated internal panel on the right side of the workspace, not a permanent right sidebar. It must keep visible outer margin, its own border, discreet elevation and bounded height. When minimized, it frees the occupied workspace area and remains reopenable through a small edge affordance.

## Composer

The composer is the only main input surface.

Visual requirements:

- text input remains primary;
- slash discovery appears inline and contextually;
- attachment and voice actions are visible but not dominant;
- disabled controls show factual reasons;
- send state follows backend/stream lifecycle.

In Slice 2 the composer is compact and lower-centered. Text is operational. Attachment, slash discovery, microphone and Conversation Mode controls may be visible only as disabled or unavailable future affordances.

## Insight

Insight should be utilitarian and calm:

- hardware facts;
- provider status;
- local model compatibility;
- recommendations with reasons;
- degraded/unavailable states;
- no speculative “can run” claims.

Slice 9 implementation rules:

- Insight is an elevated internal surface over the workspace, not page navigation.
- Opening Insight preserves Presence/Activity and Conversation Log state behind it.
- The panel has visible margins, its own border, discreet elevation, a slightly distinct dark background and responsive bounds that avoid the composer.
- It opens from the existing sidebar Insight affordance and closes through `×` or `Esc`.
- Refresh is manual only; no polling loop is introduced.
- Hardware/model/provider data is rendered as backend facts. Recommendation groups distinguish `recommended`, limited/possible and unavailable/not-recommended states without implying installation.

## Settings

Settings follows the same elevated-surface family as Conversation Log and Insight:

- internal panel over the workspace, not navigation;
- visible margins, border, discreet shadow and slightly distinct dark background;
- close through `×` and `Esc`;
- responsive bounds that avoid the composer;
- low-density sections with only real settings;
- explicit Save for backend-owned and frontend-owned settings.

Settings should not become a permanent sidebar, dashboard or command page. It must not introduce fake toggles for notifications, attachments, advanced panels, packaging or titlebar/window controls.

## Notifications

Notifications are a header/top-surface affordance, not a sidebar item and not page navigation.

Slice 11 implementation rules:

- the bell lives in the titlebar/header before the window controls;
- unread count appears as a discreet badge with textual accessible label, not color-only state;
- opening the bell shows an elevated internal popover inside Synapse;
- the popover uses visible margin, its own border, subtle elevation and a dark background distinct from the workspace;
- loading, empty, degraded and error states remain explicit;
- approval notifications use amber attention language but do not provide approval resolution controls;
- refresh is user-initiated and must not introduce aggressive polling;
- the popover must not reset Presence, Activity, Conversation Log, Conversation Mode or project state.

## Titlebar / window controls

The custom titlebar keeps the current visual language. The titlebar surface is draggable; the minimize, maximize/restore and close buttons are explicitly no-drag click targets. The maximize glyph may switch to a restore glyph when the real BrowserWindow state is maximized.

## Motion and accessibility

Motion must support `reduced-motion`:

- no essential information communicated only by animation;
- provide textual status for all operational states;
- avoid high-frequency flashing;
- keep particle density bounded;
- maintain readable contrast.

## Renderer expectations

The renderer receives a visual projection only:

```text
application facts → visual projection → scene state
```

The renderer must not own backend truth. It can own camera, positions, transitions, and animation timing only.
