# PLAN — Colab Worker Pool / VieNeu First

Date: 2026-09-23
Project: C:\Coder\tts-voice-cloning-OMNI
Companion handoff: HANDOFF-COLAB-WORKER-POOL-2026-09-23.md

## Objective

Add an ephemeral remote GPU execution layer to Colin TTS Studio so the same desktop app can use temporary Google Colab GPU runtimes from several independent Google AI Pro accounts without reconfiguring the whole application for each account.

V1 proves the architecture with VieNeu v3 Turbo.

The plan deliberately separates:
- model/provider behavior;
- execution target;
- worker identity;
- endpoint transport;
- job durability.

## Phase 0 — Baseline and design lock

### Tasks

- Inspect current git status and preserve unrelated work.
- Run current remote/provider tests:
  - `tests/test_higgs_remote.py`
  - `tests/test_generation_concurrency.py`
  - `tests/test_control_policy.py`
  - relevant VieNeu tests.
- Document current passing/failing baseline.
- Map current request flow:
  - UI
  - GenerationSettings
  - AppController
  - TtsService
  - ProviderDescriptor
  - BaseTtsEngine
  - output/history pipeline.
- Decide naming:
  - `ExecutionTarget`
  - `ComputeWorker`
  - `WorkerCapabilities`
  - `WorkerRegistry`
  - protocol version.

### Acceptance

No source behavior changed yet.
Baseline is reproducible.

## Phase 1 — Generic worker domain model

### Goal

Represent remote compute independently of Higgs and Colab.

### Suggested additions

Create core models/schemas for:
- worker ID;
- display name;
- execution target;
- endpoint;
- status;
- last heartbeat;
- GPU metadata;
- supported engines/models;
- protocol version;
- max concurrency;
- feature flags.

Prefer shared schema location already used by Core/UI/MCP.

Example conceptual shape:

```python
WorkerCapabilities(
    protocol_version="1",
    worker_id="...",
    worker_type="colab",
    gpu_name="NVIDIA L4",
    vram_mb=23034,
    engines=["vieneu"],
    models=["vieneu_v3_turbo"],
    max_concurrency=4,
    supports_batch=True,
    supports_streaming=False,
)
```

Do not include Google credentials.

### Persistence

Add a small worker settings/state store.

Persist only stable desktop-side metadata:
- known worker label;
- worker token if needed;
- latest endpoint;
- last seen;
- user preference.

Endpoint is replaceable.

### Tests

- schema roundtrip;
- unknown future fields tolerance where appropriate;
- state migration/defaults;
- no secret leakage in repr/log output.

## Phase 2 — Worker registry and pairing

### Goal

A Colab runtime can announce itself without manual URL copy/paste.

### V1 options

Preferred:
- lightweight registry service;
- short-lived pair code;
- worker exchanges pair code for worker credential;
- worker posts registration + heartbeat;
- desktop polls or refreshes registry.

If external registry adds too much scope, implement local/manual endpoint registration first behind the same interface, then add hosted pairing without redesign.

### Pair flow

Desktop:
1. create pair code;
2. show expiry;
3. poll pair state.

Worker:
1. submit pair code;
2. receive worker ID/token;
3. register current endpoint and capabilities;
4. heartbeat periodically.

Desktop:
1. worker appears;
2. endpoint becomes selectable;
3. endpoint changes update same worker instead of creating duplicates.

### Tests

- expired code rejected;
- used code rejected;
- endpoint refresh;
- heartbeat timeout -> offline;
- same worker reconnect -> same logical worker;
- unknown/invalid token rejected.

## Phase 3 — Worker protocol server

### Goal

Create a reusable remote worker process that can run locally first and then on Colab.

Suggested location:
- `remote_worker/`
or a project-consistent package under `src/`.

### Required HTTP surface

At minimum:
- `GET /health`
- `GET /capabilities`
- `POST /v1/tts/jobs`
- `GET /v1/tts/jobs/{job_id}`
- `POST /v1/tts/jobs/{job_id}/cancel`
- output/result download

Optional compatibility adapter:
- `POST /v1/audio/speech`

### Job rules

- client-supplied idempotency key or stable chunk ID;
- repeat submission of completed chunk returns existing result;
- worker can report queued/running/succeeded/failed/cancelled;
- output metadata includes sample rate, duration and checksum if practical.

### Local fake worker

Before Colab:
- start worker on localhost;
- use a fake engine returning deterministic WAV;
- exercise full desktop routing;
- simulate disconnect/reconnect.

This is mandatory before cloud testing.

## Phase 4 — VieNeu remote adapter

### Goal

Reuse existing VieNeu model/provider semantics while execution occurs on remote GPU.

Avoid duplicating VieNeu tuning schema.

### Design

Current local model remains:
- `vieneu_v3_turbo`

Add execution choice rather than a duplicate model if practical.

If current architecture makes that too invasive, a temporary remote model ID is acceptable only if internal design still separates worker execution for future migration.

Remote worker should:
- install/load `pnnbao-ump/VieNeu-TTS-v3-Turbo`;
- run CUDA path;
- accept fixed voice;
- accept profile/reference audio as supported;
- honor supported provider options;
- return normal audio artifact.

### Desktop pipeline

Preserve:
- input normalization;
- chunk/job identity;
- output naming;
- merge;
- SRT;
- generation history;
- cancellation semantics.

Do not let the remote worker become a second independent history system.

### Tests

- fixed voice;
- profile clone;
- Vietnamese;
- English/code-switch;
- provider option validation;
- invalid unsupported option;
- local and remote output contract parity.

## Phase 5 — Execution target routing

### Goal

User can choose where a compatible model runs.

Suggested choices:
- Auto
- Local CPU
- Local GPU
- Remote Worker

Later label may expose Colab specifically, but core should remain generic.

### Routing rules

For V1:
- manual worker selection is preferred;
- no automatic Google account rotation;
- no quota-aware scheduler.

Validate:
- worker online;
- model supported;
- engine version compatible;
- required VRAM/capability present;
- concurrency slot available.

If validation fails, produce actionable error.

Do not silently fall back to a different worker/model unless policy explicitly says so.

## Phase 6 — UI: Compute Workers

### Goal

Make ephemeral workers understandable.

Add a small management surface showing:
- worker name;
- type;
- engine/model capability;
- GPU;
- VRAM;
- online/offline;
- current jobs;
- max concurrency;
- last seen;
- endpoint health.

Actions:
- Pair worker;
- Refresh;
- Health check;
- Forget worker;
- Copy diagnostic info.

Job screen:
- execution target;
- worker dropdown when Remote Worker selected.

### Important UX

Do not expose implementation noise by default.

Primary flow:
```
Model: VieNeu v3 Turbo
Run on: Colab / Remote Worker
Worker: COLAB-PRO-01 · L4 · Ready
```

## Phase 7 — Canonical Colab notebook

### Goal

One notebook works across all eligible Google accounts.

Suggested files:
- `colab/Colin-TTS-Colab-Worker.ipynb`
- `colab/README.md`
- bootstrap script kept in normal source so notebook cells stay thin.

### Notebook config cell

Keep it short:

```python
WORKER_LABEL = "COLAB-PRO-01"
PAIR_CODE = "..."
ENGINE = "vieneu"
```

Optional:
- model cache mode;
- tunnel mode.

### Run All sequence

1. verify GPU runtime;
2. print `nvidia-smi` summary;
3. verify minimum VRAM;
4. clone/update pinned worker source;
5. install worker deps;
6. configure Hugging Face cache;
7. download/restore VieNeu revision;
8. start worker server;
9. start supported temporary tunnel;
10. health test locally and externally;
11. pair/register worker;
12. start heartbeat;
13. print READY summary.

### Stop section

Provide an explicit final cell / command:
- stop worker;
- stop tunnel;
- flush outputs if any;
- unregister/mark offline if possible;
- tell user to use Colab runtime disconnect/delete when finished.

Do not attempt to manage Google login.

## Phase 8 — Cache strategy

### Goal

Reduce repeated setup cost across fresh Colab VMs.

### V1

- Hugging Face cache with pinned revisions;
- optional durable archive/cache;
- manifest includes model ID, revision, expected major files.

Do not require Drive mount.

If Drive cache is supported:
- optional;
- one controlled cache root;
- no personal absolute paths hardcoded;
- verify before extraction;
- fall back cleanly when unavailable.

Measure whether caching actually saves time before adding complexity.

## Phase 9 — Durable chunk/resume

### Goal

A dead Colab session does not waste already generated audio.

### Desktop responsibilities

- stable parent job ID;
- stable chunk IDs;
- completed chunk manifest;
- checksum or file existence validation;
- retry queue for missing chunks.

### Worker responsibilities

- idempotency per chunk/job key;
- return existing completed result on safe retry;
- avoid duplicate generation where possible.

### Failure states

Represent separately:
- worker offline;
- timeout;
- generation error;
- cancelled;
- incompatible worker;
- result download failed.

### Test

Kill fake worker after N chunks.
Restart a new worker.
Resume and verify only missing chunks run.

## Phase 10 — Real Colab smoke test

### Test matrix

GPU:
- L4 preferred;
- record actual GPU if another type is allocated.

Cases:
1. fixed Vietnamese voice;
2. English/code-switch;
3. profile clone;
4. 10+ chunk batch;
5. concurrent requests if supported;
6. forced tunnel interruption;
7. runtime reconnect with changed URL;
8. resume partial job.

Record:
- notebook bootstrap time;
- dependency install time;
- model download/restore time;
- model load time;
- first audio latency;
- generation wall time;
- audio duration;
- RTF;
- GPU memory;
- tunnel overhead;
- retry result.

Store report under:
- `plans/reports/`

Suggested:
- `plans/reports/COLAB-VIENEU-V1-SMOKE-2026-xx-xx.md`

## Phase 11 — Harden V1

### Tasks

- concise error messages;
- redact worker tokens from logs;
- stale worker cleanup;
- endpoint update race handling;
- concurrency guard;
- request size limits;
- reference audio size validation;
- cancellation verification;
- test full suite;
- documentation.

### Release gate

Do not call it complete until the same notebook is tested from at least two distinct Google accounts without source modification.

## Phase 12 — OmniVoice expansion

Only after VieNeu V1 is stable.

Add:
- OmniVoice base;
- preferred Vietnamese fine-tune(s);
- remote worker capability entries;
- reference audio/profile path;
- benchmark against local behavior.

Do not fork the worker protocol.

## Phase 13 — Higgs unification

Goal:
- keep existing `higgs_remote` fully working;
- optionally adapt existing Higgs endpoint into generic worker representation;
- do not regress SGLang/Boson/custom gateway support.

Because Higgs is already remote-capable, this phase is architecture cleanup/integration, not a prerequisite for Colab V1.

## Phase 14 — Multi-worker scheduling

Later only.

Possible modes:
- manual;
- least busy;
- round robin;
- split batch.

Still schedule workers, not Google accounts.

Do not implement CCU quota scraping unless an official supported API exists.

## Recommended implementation order

Strict order:

```
0 baseline
1 worker schemas
2 registry/pairing interface
3 local fake worker
4 VieNeu remote adapter
5 execution routing
6 worker UI
7 canonical Colab notebook
8 cache optimization
9 resume/idempotency
10 real Colab test
11 harden V1
12 OmniVoice
13 Higgs unification
14 scheduling
```

## V1 acceptance checklist

- [ ] Existing local generation still passes.
- [ ] Existing Higgs remote tests still pass.
- [ ] Worker protocol is generic, not Colab-specific.
- [ ] Pair code can attach a changing endpoint to one logical worker.
- [ ] Worker offline status is visible.
- [ ] VieNeu v3 Turbo can run remotely on GPU.
- [ ] Fixed voice works.
- [ ] Profile clone works.
- [ ] Vietnamese sample works.
- [ ] English/code-switch sample works.
- [ ] Long-form multi-chunk job works.
- [ ] Completed chunks survive worker loss.
- [ ] Resume sends only incomplete chunks.
- [ ] Same notebook works for a second Google account.
- [ ] No Google password/session data stored in app.
- [ ] Stop procedure is clear.
- [ ] User is reminded to disconnect/delete Colab runtime when done.
- [ ] Documentation is updated.
- [ ] Smoke report is saved.

## Codex first task

Start with Phase 0 only, then produce a short implementation note before broad refactors.

Specifically:
1. inspect git status;
2. run relevant tests;
3. map existing classes/files involved;
4. identify the smallest schema changes for a generic worker abstraction;
5. report proposed file changes;
6. then proceed to Phase 1 unless a blocking architectural issue is found.

Do not reset or rewrite unrelated work.
Do not commit or push unless explicitly requested by the user.
