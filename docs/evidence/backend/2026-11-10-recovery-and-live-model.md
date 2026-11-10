# Backend recovery and real-model validation

Date:2026-11-10. Integrated backend only; no frontend or release claim.
Charter: CR-001/004, MI-001–007, SK-001–004, SE-001/005/006,
MM-001/002, PL-001/004/006, QA-001–003.

## Replacement, rollback and recovery

Code `acbea8a`, corrected at `46585fa`, independently reviewed with no remaining
Important findings in the scoped correction. The original review found a restore
reservation bug; the new overlapping-intent binary test reproduced it before
the fix and passed afterward. A second negative test verifies mismatched Skill
pins specifically on replacement and restore, with unchanged target bytes.

Approved replacement requires exact old/new hashes and a verified-backup policy.
The same exclusive no-follow handle captures original bytes/identity, which Core
persists and verifies before mutation. Restore refuses changed identity/content,
bad backup, revoked mission and another pending operation's target reservation.
Recovery commands inspect, finalize, restore or safely release a verified
no-effect intent. Request/mode digest changes conflict after restart.

Evidence at the correction:22 default Core binary tests and26 feature-fault Core
tests. Earlier full run also passed7 AI tests; final generation run below covers
9 AI tests. Opt-in faults cover selected prepare/write/confirmation exits.
This is bounded Windows fixed-NTFS in-place update, not atomic publication or
power-loss certification. Unexpected partial content and legacy intents retain
explicit recovery limits. No user/project production files were used in tests.

## Per-model generation settings

Code `47809b0`, independently reviewed with no Important findings in scope.
Public protocol remainsv1, internal worker isv2; storage schemav5. Optional
generation settings preserve legacy requests and are validated and snapshotted
per job. The worker digest covers output limit, reasoning preference and timeout.
HTTP socket/operation timeout is separate from Core's global supervisor limit
(configured timeout plus5000ms). Cancellation remains independent.

Reported full default regression:9 AI binary tests,22 Core binary tests and6
Python tests; formatting passed. Fixtures prove parameter delivery; an arbitrary
compatible server can ignore a field. No universal provider attestation is claimed.

## Actual Core → Python → local model journey

An owned isolated model alias was loaded from existing local files, CPU only,
1024-token context and one slot, then explicitly unloaded after each validation.
No weights downloaded and no external inference. Source model: local Qwen3.5
4B Q4_K_M. Settings:16 output tokens,15000ms timeout,reasoning_effort none.

The actual Core binary accepted model registration and chat commands via its
stdin/stdout protocol. Two Core processes were used in succession against the
same state to test history continuation. A random marker was generated at runtime:

| Observation | Actual result |
|---|---|
| First turn defines `ZAFIR-140F95` and asks for acknowledgement | `PRONTO`,4.716s |
| Core closes, reopens and is asked only for the previous keyword | `ZAFIR-140F95`,2.979s |
| Saved history after second turn | four ordered messages |
| Third turn immediately cancelled, Core closed/reopened | cancelled remains persisted; five messages, no added assistant answer |

Binary SHA256:
`8b1e481351a2d6b3054c299c150ca509483d69376a4a429e13614008d9bf4594`.
Exact receipt SHA256:
`f2294e9ed078455c8f4127e8b86fb97c6cc23d3983dd99a7b55e8fe32e33890d`.
The script/receipt/executable are retained in ignored execution artifacts under
`.superpowers/sdd/2026-11-09-integrated-backend/live-model/`; receipt subdirectory
`fcb7612fe7224b2a83923aa1f8734a15`. Earlier short OK/OK smoke also passed.

Independent read-only review verified those hashes and that the script calls
the Core executable rather than HTTP or a fixture, including process restarts,
command/responses and stored cancellation/history. The reported source commit
is execution metadata, not cryptographic reproducible-build proof; local service
identity/load/unload was observed by the controller, not independently rerun by
the reviewer. Immediate cancellation does not prove mid-generation interruption.
These single tiny examples are not latency, language or whole-model certification.

## Next integration work

Automatic canonical memory learning is in progress and is not established by
this history test. Skill-guided generation, natural-language mission planning,
model routing/temporary Swarm, voice, browser, packaging and platform execution
remain separate outstanding backend obligations. All remain in the one Core.
