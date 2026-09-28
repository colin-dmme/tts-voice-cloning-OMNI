# HANDOFF — Google Colab Remote Compute for Colin TTS Studio
## ZeroTTS CPU Offload First, Studio Integration Second

**Date:** 2026-09-28
**Project:** `C:\Coder\tts-voice-cloning-OMNI`
**Current branch:** `codex/upgrade-vieneu-v3-3.6.4`
**Status:** Ready for Codex audit + implementation
**Primary requirement:** Use Google Colab as remote CPU/GPU compute so the local PC does not carry TTS inference load. Colin TTS Studio remains the only user-facing workflow and source of truth.

Related historical documents:
- `HANDOFF-COLAB-WORKER-POOL-2026-09-23.md`
- `PLAN-COLAB-WORKER-POOL-2026-09-23.md`
- `docs/zerotts-engine.md`

This document supersedes the old sequencing decision that said "VieNeu first, ZeroTTS local only". The generic architecture ideas in the old files remain useful, but the new implementation order is intentionally:

1. Prove Google Colab as a generic remote compute worker using **ZeroTTS on remote CPU**.
2. Integrate that compute path into **Colin TTS Studio** while preserving all Studio workflow logic.
3. After the architecture is stable, extend the same compute abstraction to GPU-oriented models such as VieNeu / OmniVoice / Higgs.

---

# 0. Read this first — exact user intent

The user does **not** want to move the Colin TTS Studio workflow into Google Colab.

Google Colab is only a remote compute resource that replaces or supplements local CPU/GPU.

The user still wants to do all normal work inside Colin TTS Studio, including:
- import text/files;
- select provider/model;
- select fixed voice/profile where supported;
- pronunciation rules;
- document/project organization;
- queue management;
- output naming;
- job progress;
- retries/resume;
- history;
- SRT generation;
- merge/finalization;
- all current UI interactions.

Colab must **not** become a second TTS application with its own project/import/history/UI workflow.

The target mental model is:

```text
COLIN TTS STUDIO (local PC)
│
├─ user workflow / project state / queue / SRT / merge / history
│
└─ sends inference work
       │
       ▼
GOOGLE COLAB REMOTE COMPUTE WORKER
│
├─ model runtime
├─ CPU or GPU compute
├─ model-specific preprocessing/inference
└─ returns audio/result
       │
       ▼
COLIN TTS STUDIO
└─ continues existing pipeline
```

The main product goal is **offload compute from the local machine**, not redesign the Studio workflow.

---

# 1. Verified current project state

## 1.1 Working tree is dirty — preserve it

At handoff time the repo is on:

```text
## codex/upgrade-vieneu-v3-3.6.4
```

and has many modified/untracked files, including ZeroTTS, VieNeu, MCP, UI and documentation work.

Examples include:
- `README.md`
- `CHANGELOG.md`
- `config/models.yaml`
- `src/omni_tts_core/provider_registry.py`
- `src/omni_tts_core/provider_options.py`
- `src/omni_tts_core/service.py`
- `src/omni_tts_core/engines/preset_onnx_engine.py`
- `src/omni_tts_core/worker_installation.py`
- Qt/Tkinter UI files
- MCP files
- `engines/zerotts_worker/`
- `engines/zerotts_gguf_worker/`
- ZeroTTS tests
- old Colab plan/handoff files

**Do not run destructive cleanup.**

Do not:
- `git reset --hard`
- `git clean -fd`
- restore broad groups of files without first reading the diff
- checkout another branch in a way that discards current work
- overwrite unrelated work to simplify implementation

Before editing:
1. inspect `git status`;
2. inspect relevant diffs;
3. read files before patching;
4. isolate new code where practical;
5. preserve unrelated modifications.

If commits are created, keep Colab/remote-compute work logically separated from unrelated existing changes wherever practical.

---

## 1.2 ZeroTTS integration already exists

The project currently contains:
- official ZeroTTS 202M ONNX integration;
- GGUF F32 / Q8_0 / Q4_0 variants;
- isolated workers under `engines/`;
- provider metadata and controls;
- long-form/native preprocessing behavior;
- MCP coverage and integration tests.

Relevant files include:
- `docs/zerotts-engine.md`
- `engines/zerotts_worker/`
- `engines/zerotts_gguf_worker/`
- `install_zerotts_worker.bat`
- `install_zerotts_gguf_worker.bat`
- `scripts/install_zerotts_worker_linux.sh`
- `scripts/install_zerotts_gguf_worker_linux.sh`
- `tests/test_zerotts_integration.py`
- `tests/test_zerotts_gguf_integration.py`

Current ONNX worker code has been verified to initialize ZeroTTS with:

```python
providers=["CPUExecutionProvider"]
```

The current ZeroTTS release/integration is therefore CPU-oriented. Do **not** assume that using a Colab T4/L4/A100 makes ZeroTTS GPU accelerated.

For ZeroTTS Phase 1:
- use Colab CPU compute;
- do not request a GPU accelerator unless an explicit source audit proves a supported CUDA path;
- optimize remote CPU usage, model residency, startup and transport overhead.

GPU Colab becomes important later for GPU-capable engines.

---

## 1.3 Existing ZeroTTS behavior that must be preserved

According to `docs/zerotts-engine.md` and current integration:
- ZeroTTS outputs mono 48 kHz audio;
- ONNX provider exposes many provider-specific controls;
- it has native text preprocessing;
- its long-form logic is model/provider specific;
- voice packs are fixed latent voices;
- open-source ZeroTTS does not currently expose normal WAV/profile voice cloning;
- Studio/Core already owns output, SRT, history, queue and common workflow behavior.

Important architectural nuance:

**Studio owns workflow-level chunking/job identity.
Worker may still perform model-specific internal preprocessing/splitting required by ZeroTTS.**

Do not blindly move ZeroTTS-specific native preprocessing into the Studio layer merely to make the worker "dumb". The remote worker should own whatever is genuinely part of the provider/model runtime contract.

---

# 2. Non-negotiable architecture boundaries

## 2.1 Colin TTS Studio remains source of truth

Studio must own:
- imported documents/files;
- project metadata;
- queue;
- stable job IDs;
- stable inference-unit/chunk IDs;
- original source text;
- pronunciation preset snapshots;
- output destination;
- history;
- retry/resume state;
- final SRT;
- merge/finalization;
- user-visible progress.

If Colab disappears, the Studio must still know what completed and what remains.

---

## 2.2 Colab owns compute/runtime responsibilities only

A Colab worker may own:
- installing/bootstrapping its runtime;
- model download/cache;
- loading model resident in RAM;
- CPU/GPU inference;
- model-specific preprocessing;
- temporary inference artifacts;
- worker-local diagnostics;
- health/capabilities;
- request cancellation;
- returning audio and metadata.

A Colab worker must not become the authoritative owner of:
- a book/project;
- Studio queue state;
- SRT history;
- final output naming;
- application history;
- user document import.

---

## 2.3 Provider/model is separate from execution target

Do not create fake provider duplication such as:
- ZeroTTS Local
- ZeroTTS Colab
- VieNeu Local
- VieNeu Colab

The conceptual model should become:

```text
Provider / Model
    +
Execution Target
```

For example:

```text
Provider: ZeroTTS
Model: ZeroTTS 202M ONNX
Execution target: Local CPU | Google Colab
```

Later:

```text
Provider: VieNeu
Model: VieNeu v3 Turbo
Execution target: Local GPU | Google Colab
```

The execution abstraction should be generic enough for future RunPod / Vast / dedicated server workers, even if only Colab is implemented initially.

---

# 3. Target architecture

```text
                         COLIN TTS STUDIO
                  local UI + workflow + persistence
                               │
                               │
                  stable inference request
                               │
                 ┌─────────────┴─────────────┐
                 │                           │
           LOCAL EXECUTION              REMOTE EXECUTION
                 │                           │
         CPU / local GPU              ComputeWorker API
                                             │
                                      Google Colab VM
                                             │
                                  ┌──────────┴──────────┐
                                  │                     │
                              CPU runtime           GPU runtime
                                  │                     │
                               ZeroTTS             VieNeu / etc.
```

The first vertical slice is:

```text
Studio-independent smoke client
        ↓
ComputeWorker API
        ↓
Colab CPU
        ↓
ZeroTTS ONNX
        ↓
WAV/PCM + metadata returned
```

After that is stable, wire the same path into Studio.

---

# 4. Two-part implementation plan

# PART 1 — Google Colab Remote Compute Foundation
## Goal

Build and validate a **real remote compute worker on Colab** using ZeroTTS ONNX on Colab CPU.

Part 1 is deliberately **not yet a Colin Studio UI feature**.

However, it must be designed specifically so Part 2 can integrate it without redesign.

Part 1 is complete when the local PC can submit a ZeroTTS inference request over HTTP to a Colab runtime, receive valid audio, and local inference load is avoided.

---

## Phase 1A — Audit and contract lock

Before coding, Codex must inspect:
- current ZeroTTS worker implementation;
- existing subprocess engine contract;
- provider option schemas;
- current request/result structures;
- existing Higgs remote implementation;
- current remote endpoint helpers;
- generation concurrency behavior;
- cancellation and job/history architecture.

Priority files to inspect:
- `src/omni_tts_core/engines/base.py`
- `src/omni_tts_core/engines/preset_onnx_engine.py`
- `src/omni_tts_core/remote/endpoint.py`
- `src/omni_tts_core/engines/higgs_remote_engine.py`
- `src/omni_tts_core/remote/higgs_sglang.py`
- `src/omni_tts_core/generation_concurrency.py`
- `src/omni_tts_core/service.py`
- `src/omni_tts_core/provider_registry.py`
- `src/omni_tts_core/provider_options.py`
- `engines/zerotts_worker/`
- `docs/zerotts-engine.md`
- existing relevant tests.

Deliverable:
- a short architecture audit;
- exact reusable pieces;
- exact gaps;
- protocol proposal;
- risk list.

Do not duplicate Higgs-specific concepts if a generic abstraction can reuse proven code.

---

## Phase 1B — Define generic ComputeWorker protocol

Create a protocol that is not named after Colab or ZeroTTS.

Suggested concepts:
- `ComputeWorker`
- `WorkerCapabilities`
- `RemoteTtsJob`
- protocol version
- worker ID
- execution backend
- supported model IDs
- max concurrency
- supported output formats

Minimum HTTP endpoints:

```text
GET  /health
GET  /capabilities

POST /v1/tts/jobs
GET  /v1/tts/jobs/{job_id}
POST /v1/tts/jobs/{job_id}/cancel

GET  /v1/tts/jobs/{job_id}/result
```

Optional:
- an OpenAI-style or existing compatibility route only as an adapter, not as the core protocol.

Required job states:
- queued
- running
- succeeded
- failed
- cancelled

Required request properties:
- protocol version;
- client job ID;
- stable idempotency key / inference-unit ID;
- model ID;
- text;
- voice/fixed voice payload as supported;
- provider options;
- requested output format;
- optional request metadata for tracing.

Required result metadata:
- job ID;
- status;
- sample rate;
- channels;
- duration;
- audio format;
- checksum if practical;
- timing diagnostics;
- model/runtime identity.

The worker must reject unsupported model/options clearly rather than silently ignoring them.

---

## Phase 1C — Build canonical Colab bootstrap

Add one canonical notebook, suggested location:

```text
colab/Colin-TTS-Compute-Worker.ipynb
```

Prefer generating the notebook from maintainable source/scripts if practical, instead of embedding large duplicated logic only inside notebook cells.

User experience should be:

1. open notebook;
2. choose runtime;
3. Run All;
4. worker becomes ready.

For ZeroTTS first:
- recommend normal Colab CPU runtime / no hardware accelerator;
- detect CPU/RAM;
- install minimal required dependencies;
- fetch/pin worker source;
- fetch model if needed;
- start worker server;
- expose remote endpoint;
- display READY state.

Expected ready output example:

```text
COLIN TTS COMPUTE WORKER — READY
Worker ID: ...
Runtime: Google Colab
Backend: CPU
Model: ZeroTTS 202M ONNX
Sample rate: 48000
Endpoint: https://...
Auth: enabled
```

Do not add text import/project UI to the notebook.

---

## Phase 1D — ZeroTTS runtime on Colab CPU

Adapt/reuse the existing ZeroTTS worker implementation so the remote worker can:
- install on Linux/Colab;
- download the pinned model revision;
- load the model once;
- keep it resident across requests;
- use `CPUExecutionProvider`;
- accept the same meaningful provider options currently supported by Colin TTS Studio;
- return valid 48 kHz output.

Do not reload the model for each request.

Benchmark at least:
- 2 threads;
- 4 threads;
- 8 threads;
- warmup on/off where relevant;
- short text;
- medium text;
- longer inference unit.

Record:
- model download time;
- worker startup time;
- model load time;
- warmup time;
- TTFA where measurable;
- total inference time;
- RTF;
- peak RAM if practical.

Do not assume more threads are faster.

---

## Phase 1E — Model caching strategy

Colab local storage is ephemeral.

Implement caching as an optimization, not a correctness requirement.

Baseline:
- direct model download to local Colab filesystem.

Optional cache:
- Google Drive or another persistent cache.

If Drive cache is used:
- copy from Drive to local Colab disk before inference;
- do not run heavy model inference directly against mounted Drive files;
- validate model revision/manifest;
- fall back to normal download when cache is missing or invalid.

Benchmark:
- direct Hugging Face download;
- persistent cache restore.

Choose the simpler/faster default based on measured result.

---

## Phase 1F — Remote exposure and authentication

The worker must be reachable from the local PC.

V1 may use a temporary tunnel such as TryCloudflare if appropriate.

Requirements:
- HTTPS endpoint;
- random/short-lived bearer token or equivalent;
- no Google account credentials stored in Studio;
- token must not be printed into normal logs unnecessarily;
- health endpoint may be less sensitive, but job/result endpoints require auth;
- endpoint changing after runtime restart is treated as normal.

Do not design Colab as a permanent 24/7 server.

Provide a clean STOP/shutdown procedure.

---

## Phase 1G — Local smoke-test client, still outside Studio integration

Before changing Studio routing/UI, add a minimal test client/script that can run on the local PC and prove:

```text
local request
→ HTTPS
→ Colab worker
→ ZeroTTS inference
→ result download
→ local WAV validation
```

This client exists only for engineering validation.

It should test:
- health;
- capabilities;
- normal request;
- provider options;
- repeated request/idempotency;
- invalid option;
- cancel;
- worker restart/offline handling;
- audio integrity.

This is the critical boundary between Part 1 and Part 2.

---

## Phase 1H — Stress/resilience test

Run enough requests to establish that the architecture is usable for long-form workflows later.

Test:
- sequential requests;
- limited concurrent requests;
- repeated jobs after model is warm;
- tunnel interruption;
- worker process restart;
- Colab runtime loss;
- request timeout;
- partial result cleanup;
- cancellation.

The local smoke client should not lose its own record of submitted job IDs merely because the remote worker disappears.

---

## Part 1 acceptance criteria

Do not claim Part 1 complete until all of these are demonstrated:

1. A fresh Colab runtime can be started with documented simple steps / Run All.
2. ZeroTTS worker installs successfully on Colab Linux.
3. Model revision is pinned/validated.
4. ZeroTTS loads once and remains resident.
5. Worker uses remote Colab CPU, not local CPU, for inference.
6. Local PC can call `/health` and `/capabilities`.
7. Local PC can submit a real TTS job.
8. Valid 48 kHz audio is returned/downloaded.
9. Supported provider options are preserved.
10. Unsupported options fail clearly.
11. Authentication is enabled.
12. Cancellation works or has clearly documented limitations.
13. Runtime restart/offline state is handled predictably.
14. Benchmark results are recorded.
15. Local-vs-remote output contract parity is tested.
16. No Colin TTS Studio workflow logic was moved into Colab.
17. Existing unrelated local workflows are not broken.

**Checkpoint:** Report Part 1 results before beginning invasive Studio integration.

---

# PART 2 — Colin TTS Studio Remote Compute Integration
## Goal

Make Google Colab appear inside Colin TTS Studio as an **execution target**, while the existing Studio remains the user's only normal working interface.

Part 2 begins only after the Part 1 worker protocol is proven.

---

## Phase 2A — Add execution-target domain model

Introduce a generic concept separate from provider/model.

Suggested initial targets:
- `local_cpu`
- `local_gpu`
- `remote_worker`

A `remote_worker` can carry:
- worker ID;
- display name;
- endpoint;
- auth credential reference;
- online/offline;
- last seen;
- CPU/GPU metadata;
- supported model IDs;
- max concurrency;
- protocol version.

Do not bind worker identity to Google account identity.

Do not store Google passwords/cookies.

---

## Phase 2B — Implement RemoteComputeClient

Create a core client that:
- checks health;
- reads capabilities;
- validates model compatibility;
- submits job;
- polls/streams progress;
- cancels;
- downloads result;
- validates checksum/metadata;
- maps remote errors into normal Core errors.

The client should be independent of Qt/Tkinter UI.

Use the same client from:
- UI;
- MCP path;
- tests;
- future automation.

---

## Phase 2C — ZeroTTS remote routing

For model `zerotts_202m_onnx`:
- local execution keeps current behavior;
- remote execution sends inference work to compatible worker.

Do not create a duplicate ZeroTTS model unless absolutely required by a transitional implementation.

Preferred model:

```text
provider = ZeroTTS
model = zerotts_202m_onnx
execution_target = local | remote_worker
```

Provider options should map 1:1 to the worker contract wherever supported.

---

## Phase 2D — Preserve workflow vs model-runtime boundary

The Studio owns:
- imported files;
- source text;
- queue;
- project grouping;
- pronunciation rules/snapshots;
- stable job/inference IDs;
- retry state;
- SRT;
- merge;
- output naming;
- history.

Remote worker owns:
- ZeroTTS native preprocessing needed by the provider;
- inference;
- temporary audio generation.

Do not send an entire "project" to Colab and let Colab manage it.

The unit sent remotely should be a stable inference unit selected by Studio.

If ZeroTTS internally re-splits that unit, the result contract must still allow Studio to associate the final returned audio with the stable Studio unit.

---

## Phase 2E — UI

Initial UI should be simple and explicit.

For example:

```text
Provider
ZeroTTS

Model
ZeroTTS 202M ONNX

Execution
● This computer
○ Remote Compute
```

When Remote Compute is selected:

```text
Worker
COLAB-01

Status: Online
Runtime: Google Colab
CPU: ...
GPU: none
Model: ZeroTTS 202M ONNX
Latency: ...
```

For V1, manual endpoint/token configuration is acceptable if it reduces implementation risk:

```text
Endpoint: https://...
Token: ********
[ Test connection ]
```

Do **not** block the first usable remote path on building a sophisticated pairing registry.

---

## Phase 2F — Queue / retry / resume

Studio is authoritative.

Example:

```text
Episode 01
unit 001 ✅
unit 002 ✅
unit 003 running
unit 004 pending
...
```

If Colab dies:
- completed units remain complete;
- running unit becomes retryable/unknown according to idempotency contract;
- pending units remain pending;
- reconnecting a worker resumes only missing work.

Do not restart the entire document merely because the remote worker changed endpoint.

Use stable idempotency keys so a repeated submit can safely return an already completed result when possible.

---

## Phase 2G — Output/SRT/history parity

Remote execution must feed back into the existing Studio pipeline.

The final user-visible behavior should remain:
- WAV/MP3 generation;
- SRT;
- naming;
- output folder behavior;
- queue;
- history;
- cancellation;
- pronunciation reports where applicable.

Remote execution must not introduce a separate output/history system.

---

## Phase 2H — Worker discovery/pairing, after manual remote path works

Only after manual endpoint remote execution is stable, add improved UX.

Suggested future UX:

Studio:
```text
Add Colab Worker
Pair code: N7K4-92Q
Waiting...
```

Notebook:
```text
PAIR_CODE = "N7K4-92Q"
```

Then:
- worker registers endpoint/capabilities;
- Studio sees it online;
- endpoint changes update the same logical worker;
- pair codes expire and are single-use where practical.

A lightweight registry can be implemented with Cloudflare Worker/KV or another minimal service.

Pairing is **not** a prerequisite for proving remote inference.

---

# 5. Phase 3 later — GPU models on the same worker architecture

After ZeroTTS remote CPU is stable, extend the same ComputeWorker protocol to GPU models.

Priority candidates:
1. VieNeu v3 Turbo;
2. OmniVoice variants;
3. Higgs TTS 3 / compatibility with existing remote path.

Then Colab becomes:

```text
ZeroTTS
→ Colab CPU worker

VieNeu
→ Colab GPU worker

OmniVoice
→ Colab GPU worker

Higgs
→ remote GPU worker
```

The Studio UX should remain the same execution-target abstraction.

Do not create a new architecture per model.

---

# 6. Recommended code layout

Exact names can change after audit, but prefer a generic split similar to:

```text
src/omni_tts_core/remote_compute/
    models.py
    client.py
    protocol.py
    worker_registry.py        # later
    errors.py

remote_worker/
    server.py
    jobs.py
    capabilities.py
    engines/
        zerotts.py
        vieneu.py             # later

colab/
    Colin-TTS-Compute-Worker.ipynb
    bootstrap_worker.py       # if notebook generation/bootstrap uses it

tests/
    test_remote_compute_protocol.py
    test_remote_compute_client.py
    test_remote_zerotts.py
```

Reuse existing project conventions instead if there is a more natural home after audit.

Avoid large monolithic files.

---

# 7. Suggested worker capability schema

Conceptual example:

```json
{
  "protocol_version": "1",
  "worker_id": "colab-...",
  "worker_type": "google_colab",
  "runtime": {
    "cpu": "...",
    "ram_mb": 12345,
    "gpu": null,
    "vram_mb": null
  },
  "models": [
    {
      "model_id": "zerotts_202m_onnx",
      "provider_id": "zerotts",
      "execution_backend": "cpu",
      "sample_rate": 48000,
      "supports_streaming": true,
      "supports_profile_clone": false
    }
  ],
  "max_concurrency": 1
}
```

Later GPU worker example:

```json
{
  "worker_type": "google_colab",
  "runtime": {
    "gpu": "NVIDIA L4",
    "vram_mb": 23000
  },
  "models": [
    {
      "model_id": "vieneu_v3_turbo",
      "execution_backend": "cuda"
    }
  ]
}
```

The exact schema must be versioned and tested.

---

# 8. Security requirements

V1 is personal-use oriented but must not be reckless.

Required:
- HTTPS tunnel;
- bearer token or equivalent;
- do not store Google login credentials;
- do not store browser cookies;
- avoid secret leakage in logs/repr;
- reject unauthenticated job/result requests;
- validate request size;
- validate model ID/options;
- sanitize result paths;
- prevent arbitrary filesystem access;
- no arbitrary shell execution through worker API.

Pairing later should exchange short-lived pair codes for worker credentials.

---

# 9. Performance goals and measurement

The key goal is **local resource offload**, not merely maximum raw synthesis speed.

Measure at least:

## Local side
- CPU usage while remote inference runs;
- GPU usage while remote inference runs;
- network transfer;
- request overhead.

## Colab side
- startup;
- model load;
- warmup;
- CPU/RAM;
- inference time;
- RTF;
- concurrency behavior.

## End-to-end
- submit-to-first-result;
- submit-to-complete;
- result download;
- total wall time.

Compare:
- current local ZeroTTS;
- Colab remote ZeroTTS.

A remote run may be somewhat slower yet still be valuable if it frees the local PC. Record both compute performance and offload effectiveness.

---

# 10. Testing requirements

At minimum:

## Protocol/unit tests
- schema validation;
- protocol version;
- unsupported model;
- unsupported options;
- auth missing/invalid;
- idempotency;
- job state transitions;
- cancellation;
- checksum/result metadata.

## Worker tests
- fake engine deterministic WAV;
- ZeroTTS real smoke test where environment allows;
- repeated resident-model requests;
- timeout/failure handling.

## Client tests
- health;
- capabilities;
- submit;
- poll;
- cancel;
- result download;
- offline;
- reconnect;
- duplicate submit.

## Studio integration tests
- local ZeroTTS unchanged;
- remote ZeroTTS path;
- queue continues after worker reconnect;
- final output pipeline unchanged;
- SRT/history behavior unchanged;
- UI does not expose incompatible remote workers.

Do not require live Colab for every normal test. Use a local fake worker/HTTP server for deterministic CI/unit coverage.

---

# 11. Implementation checkpoints

Use these checkpoints to avoid a huge unreviewable change.

## Checkpoint A — Audit only
Report:
- current reusable remote architecture;
- proposed protocol;
- files to add/change;
- conflicts with dirty working tree;
- risks.

## Checkpoint B — Local fake ComputeWorker
Prove generic job protocol locally without Colab.

## Checkpoint C — Real Colab + ZeroTTS
Fresh Colab Run All → remote ZeroTTS job → valid WAV on PC.

**Report benchmark and acceptance evidence here.**

## Checkpoint D — Studio Core integration
Add execution target/client/routing, still minimal UI.

## Checkpoint E — Studio UI + queue/retry
Make it usable end-to-end from Colin TTS Studio.

## Checkpoint F — Pairing/discovery
Only after manual endpoint mode is stable.

## Checkpoint G — GPU engine extension
VieNeu first unless a new audit identifies a better target.

---

# 12. Important "do not" list

Do not:
- move file import/project management to Colab;
- build a second full TTS UI in Colab;
- make Colab the source of truth for long-form jobs;
- create provider duplicates just to encode execution location;
- assume ZeroTTS uses GPU;
- consume a GPU runtime for ZeroTTS without evidence that it benefits;
- reload ZeroTTS model for every request;
- couple the protocol permanently to Colab;
- store Google credentials in the app;
- make pairing/registry a blocker for first remote inference;
- break existing Higgs remote behavior;
- break local ZeroTTS;
- reset/clean the dirty working tree;
- silently discard unsupported provider options.

---

# 13. Definition of final success

The final user experience should become:

1. User opens Colin TTS Studio on the PC.
2. User imports files and configures everything exactly in Studio.
3. User selects a model.
4. User selects execution target:
   - Local, or
   - Remote Compute / Google Colab.
5. Studio sends only inference work to Colab.
6. Colab uses its CPU/GPU and returns audio.
7. Studio performs the rest of the normal workflow.
8. If Colab disconnects, Studio retains job state and can resume missing work after reconnect.
9. Local machine avoids the heavy TTS inference load when remote execution is selected.

For ZeroTTS specifically:

```text
Colin TTS Studio
→ stable inference unit + ZeroTTS options
→ Google Colab CPU
→ ZeroTTS 202M ONNX
→ audio result
→ Colin TTS Studio output/SRT/history
```

For future GPU models:

```text
Colin TTS Studio
→ inference unit + model options
→ Google Colab GPU
→ model inference
→ audio result
→ same Studio pipeline
```

This separation — **Studio is the brain; Colab is the compute card** — is the central design rule.

---

# 14. Codex execution instruction

Start by auditing the current repository against this handoff.

Then:
1. produce a concise gap/risk assessment;
2. preserve the dirty working tree;
3. implement Part 1 in small testable checkpoints;
4. prove a real ZeroTTS Colab remote inference path;
5. report measured evidence;
6. only then begin Part 2 Studio integration;
7. keep README/CHANGELOG/docs updated as architecture becomes real;
8. run relevant tests after each checkpoint;
9. do not claim a checkpoint complete without test/smoke evidence.

When implementation choices conflict with this document, prioritize these product constraints:
- Studio remains the only normal user workflow.
- Colab is compute only.
- ZeroTTS first proves remote CPU offload.
- Execution target stays separate from provider/model.
- Job state stays durable on the Studio side.
- Existing unrelated work must be preserved.
