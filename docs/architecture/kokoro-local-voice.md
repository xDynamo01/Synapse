# Kokoro / feminine local voices

The packaged default is the ready-made feminine Kokoro catalog: 29 voices across
Brazilian Portuguese, English, Spanish, French, Italian, Japanese, Hindi and
Mandarin. `pf_dora` remains the default for Brazilian Portuguese.

## Boundary

Speech adapters retain the existing SpeechExecutionPort. Kokoro has a separate
adapter and provider, not a renamed Piper. The composition-owned local executor
launches the packaged runner with an isolated Python environment. No Torch,
Transformers, or Kokoro library is added to the main backend environment or its
dependency lock. The ONNX runtime uses CPU only and two intra-op threads. A process
ends after each synthesis, releasing model memory; cold-start cost is intentional.
WAV output is verified and returned inline, then removed in finally. Only one
request per adapter runs at a time. Unknown voice IDs are rejected, not substituted.

## Provisioning

Run `scripts/voice/install-kokoro.ps1` with Python 3.12 and uv installed. Setup
requires internet; synthesis does not. Dependencies are wheel-only, pinned and
hash-locked in `scripts/voice/requirements.txt`; the root `uv.lock` is unchanged.
Model artifacts live in `data/voice/models/kokoro`; the separate Python environment
is `data/voice/runtimes/kokoro`. Never bundle that environment into the sidecar.

When the application uses another data directory, `voice/kokoro-runtime.json`
contains an installation-owned `root` pointing to the shared voice directory.
This is separate from typed user voice settings so saving Settings preserves it.
Set `tts_provider_id` to `kokoro` and `default_tts_voice` to `pf_dora` through voice
settings. Each voice requires its matching language; unknown or masculine voice IDs
are rejected rather than silently substituted.

## Provenance and licensing

- Model: hexgrad/Kokoro-82M v1.0, Apache-2.0.
- ONNX conversion: thewh1teagle/kokoro-onnx release model-files-v1.0.
- kokoro-onnx 0.6.1: MIT; ONNX Runtime: MIT.
- Phonemizer and eSpeak NG carry GPL licensing. They remain separate components;
  a distributed commercial product must ship their notices and meet those terms.
- Package metadata reported no listed vulnerabilities for the 13 pinned packages
  on 2026-09-13. This is not an exhaustive security audit.
- Wheel-only installation runs no source build hooks. Runtime code review found
  local model loading and bundled eSpeak data, no model fetch in synthesis.
- No cloudpickle/joblib loading is used by our runner; voice arrays use NumPy's
  default pickle-disabled loading.

The retired Cadu/Jeff/Edresson pack was moved, not erased, to
`artifacts/restore-points/voice-library/synapse-default-v0.01`. It is no longer a
packaged voice library. Piper remains an optional adapter for explicit external
configuration. Tests of Piper use fixtures; real local execution covers the
Kokoro feminine catalog.

## Verification observations

Initial actual-data-directory synthesis returned Dora, 24 kHz WAV, 2304 ms of
speech, in 4441 ms including process/model startup. The Electron playback harness
played a generated Dora sample through the shipped CSP to `ended` (4.459 seconds).
This validates output and playback, not an entire microphone-to-model conversation.
The existing architecture graph-count gate reports 312 edges against 306; no
baseline is silently changed. The new adapter uses already-existing context edges.

Final checks: 45 voice/execution tests passed, Ruff passed, global Mypy passed
for 815 source files; frontend lint and 33 shell tests passed; diff check passed.
Architecture suite: six passed, one existing graph-count mismatch (312/306).
The frozen sidecar built successfully and its API listed the packaged Kokoro
feminine voices as ready;
the Electron harness synthesized through that API and played to ended (1.152 s).
The packaged resources contain only kokoro-feminine-v1, and no Torch, Transformers,
SentenceTransformers or kokoro_onnx directory is present in the sidecar. The
optional repository-runtime startup reported canonical-root mismatch in the
isolated smoke data directory; it did not prevent the speech API smoke.

Sources: https://github.com/thewh1teagle/kokoro-onnx and
https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md.
