# Skill guidance — actual Core and local model

Date2026-11-10. Runtime source `26e5e8e`. Windows, Rust1.96/MSVC, Python3.14.3.
This task integrates immutable registered domain guidance into conversations;
it does not implement autonomous discovery, evolution, arbitrary executable
Skills or complete mission execution.

`conversation_start.skill` optionally supplies the exact project/id/version/
digest. Core resolves it before appending the human message. The worker receives
serialized instructions and pin as untrusted guidance, without tool/permission
declarations. This adds no dispatch, approval or file-effect path. The pin is
durable in schema7; absent pins preserve old request serialization and receipt
behavior. Guidance counts toward the existing message/context limits, including
the wrapper's UTF8 size. Automatic learning continues to receive only the human
source message.

Verification:42 Rust tests with all features (16 actual-binary AI and26 Core/tool),
7 Python tests, formatting and whitespace checks passed. Focused RED tests
demonstrated the absent optional API and wrapper overflow before the fixes.
Tests cover exact delivery, wrong scope/digest/version, atomic budget rejection,
source-only learning, immutable versions, request replay, migration and restart.

The controller then built the default-feature binary and ran the actual local
model through Core and its supervised Python worker. One existing Qwen3.5 4B
alias ran CPU only, context1024, parallel1; explicit generation32tokens,
15000ms, reasoning none. No weights were downloaded and no HTTP fixture was used.

A random verification code appeared only in the registered Skill. The human
asked for that code without repeating it; the model replied exactly
`LIRA-7CC09D`. The returned job carried the expected Skill pin and successful
result. Restarting Core preserved the identical result and pin. This demonstrates
guidance reaching and affecting this model's output, not a general prompt
obedience guarantee or the security boundary. Authority remains enforced in Core.

Ignored artifacts under `.superpowers/sdd/2026-11-10-skill-guided-conversation/`:

- `live_guidance.py`: actual subprocess/RPC controller.
- `synapse-backend-guidance.exe` SHA256
  `88709a71285da50e3e11c69b38e2484732b00eae5b0dba9d87eff2a005e20fb6`.
- `live-1e677d605bd34ffc9a7df53998b94cdd/receipt.json` SHA256
  `a778f2905ce62c0a0657c0c0bb0fdf3bafeb4ee94a2736f4f6cc42ac38ef7d76`.

Build/source association and local server alias were observed by the controller,
not independently reproduced or cryptographically attested. The validation alias
was unloaded afterward; `lms ps` showed no loaded models. Independent task and
artifact review is recorded in the plan ledger; acceptance requires that review.

Explicit canonical context-to-conversation delivery is the next task. Frontend,
planner, routing, temporary Swarm and voice/browser operation remain subsequent
backend work; this evidence does not declare the entire backend complete.
