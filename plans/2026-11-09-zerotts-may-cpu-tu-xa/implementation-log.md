# Implementation ledger — CPU worker chung, 09/11/2026

Plan: C:/Coder/tts-voice-cloning-OMNI/plans/2026-11-09-zerotts-may-cpu-tu-xa/plan.md

Spec: user approved implementation of one Windows/Internet CPU route for ZeroTTS Official, Piper ONNX and VieNeu v3; shared broker, queue, controls and adapters, preserving local and Google/Higgs behavior.

Branches: Studio and compute service `codex/remote-cpu-worker`.
Baseline Studio HEAD: `74e1972bad522c849f82f524b3322a3f04ef1edc`; service HEAD: `0b370722b9b37c46128ccf2859c999fac29dc80a`.

Ruling: Work in the existing checkout on dedicated feature branches, preserving the unfinished authorized Colab foundation and unrelated narrative-pacing edits. A clean HEAD worktree would omit that required foundation. Cost if wrong: scoped patch integration may need manual reconciliation; no existing edits are reverted.
Ruling: The prose plan is executed as three integration units plus release/pilot. Root implements service/runtime and shared inference; one subagent owns UI/request serialization. Only one implementation subagent is dispatched at a time. Cost if wrong: interface fixes at integration; ownership boundaries prevent concurrent edits to the same file.
Ruling: Keep one durable job store/supervisor and explicit remote target; legacy wire `runtime_target=remote` remains compatible. Common modules move in small compatible steps, not a duplicate queue. Cost if wrong: migration/import alias adjustments covered by regression tests.

## Pre-flight scan

| Unit | Produces / consumes | Result |
|---|---|---|
| UI/contracts | typed remote_compute object + settings fields; consumes BrokerClient PC methods | Freeze interface in task-ui-brief.md before dispatch |
| Service/auth | PC identity/session + controls; consumes worker capabilities/lease protocol | Keep legacy Colab pairing unchanged; PC session scopes multiple allowed CPU models |
| Runtime/queue | explicit PC lifecycle, adapter dispatcher and Windows worker; consumes UI target + scoped PC session | PC never calls Google; actual WAV rate from each adapter |
| Packaging/pilot | committed allowlist source + model manifests, consumes runtime/PC auth | No runtime/token/model/account data in source package; actual second-machine pilot waits for host identification |
| UI ↔ queue | worker profile ID and CPU target snapshot | Three flat settings fields map to one typed request object; snapshot profile before job creation |
| Queue ↔ service | model/provider/options/native rate | Preserve existing request v1; add typed segments and PC capability/identity validation, keep old model support |
| Auth ↔ worker | device grant + short session | DPAPI outside source, admin-only approval/revocation, no master key on worker |

## Progress

- Baseline before changes: Studio 607 tests and 335 subtests, service 75 tests.
- Task 1: explicit CPU target in Studio and MCP, machine selector and management dialog. The task report records the UI/contract tests.
- Task 2: PC enrollment, DPAPI, scoped sessions, stop/revoke fencing and adapters. Service commits `e034b46`, `6a4624a` and `a688cb5`.
- Task 3: common queue, transport and inference in `src/colin_remote_compute/`. Colab keeps provider-specific code and compatibility imports. Studio full suite passed 632 tests and 335 subtests. Service full suite passed 81 tests.
- Task 4: the final release ZIP is `Colin-CPU-Worker-cpu-a688cb51d4ad-74e1972bad52.zip`. Windows PowerShell 5.1 exercised the upgrade path and probed all five WAVs. The packaged worker ran all five models through the Studio entry point on one Windows host with an isolated loopback broker. VieNeu clone with a generated reference WAV also passed. MCP stdio sent a TXT file to Piper and returned a real WAV. Repeating the request with the same idempotency key returned the same job.
- Task 5: independent review caught late renew callbacks and stop during warmup. Fixed the races, retained the process handle until shutdown is confirmed, and tested the late-renew case. Qt management/queue constructed successfully offscreen.
- Production: the existing broker and queue were idle. A verified SQLite backup preceded the restart. Local and public `/health` confirm PC worker and managed Colab. The authenticated PC list succeeded and both local/public unauthenticated PC list requests returned HTTP 401. One public request returned 502 while the tunnel was settling. Three successive rechecks passed.
- Windows hosts named by the user are CAROPC and ColinThinkPad. At release the production PC list is empty. No verified management connection to either host is available from this session. The first Internet job and resource measurements on each named host remain pending enrollment.
