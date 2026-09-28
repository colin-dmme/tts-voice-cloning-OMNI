# HANDOFF — Colab Worker Pool for Colin TTS Studio

Date: 2026-09-23
Project: C:\Coder\tts-voice-cloning-OMNI
Status: Design approved for implementation planning
Primary target: Google Colab paid compute attached to several Google AI Pro accounts
Initial engine priority: VieNeu v3 Turbo
Later engines: OmniVoice, Higgs TTS 3

## 1. User goal

The user has several Google accounts with eligible paid Colab compute and wants to use those accounts as temporary GPU execution capacity for Colin TTS Studio.

The experience should be simple:

1. Open the same notebook from any eligible Google account.
2. Select a GPU runtime.
3. Run all cells.
4. The notebook bootstraps the worker automatically.
5. Colin TTS Studio discovers or pairs with that worker.
6. The user sends long-form TTS jobs to it.
7. When work is finished, the user shuts down/disconnects the Colab runtime so paid compute is not left running.

The user should NOT need to:
- manually reinstall the project step by step for every account;
- manually edit source for each account;
- manually copy changing tunnel URLs into the Studio every session if this can be avoided;
- store Google usernames/passwords inside Colin TTS Studio;
- run every Google account at the same time when only one worker is needed.

## 2. Important product constraints

### 2.1 Google account scope

Each Google account owns its own Colab runtime and compute balance. Do not attempt to merge Google sessions or automate Google login/account switching.

Treat every active Colab runtime as an independent ephemeral worker.

### 2.2 Colab is ephemeral

A Colab VM can disappear, restart, change IP, lose local files, or end its session.

Therefore:
- local runtime disk is cache, not source of truth;
- worker registration must tolerate changing endpoint URLs;
- jobs must be resumable;
- output must be persisted back to the desktop app or durable storage;
- worker offline state must be normal, not exceptional.

### 2.3 Do not design Colab as a permanent always-on production server

The intended Colab mode is user-started, session-scoped GPU execution for interactive/batch work. The design should make it easy to stop the worker after jobs finish.

Do not rely on 24/7 uptime.

### 2.4 No Google credentials inside the app

Colin TTS Studio may store:
- worker ID;
- worker label;
- engine capabilities;
- endpoint URL;
- pair token or worker token;
- heartbeat timestamps;
- GPU information;
- transient job state.

It must not store:
- Google account password;
- browser session cookies;
- OAuth tokens for Google login unless a future explicit design requires and approves this.

## 3. Existing project architecture to reuse

Do not create a parallel mini-application unless unavoidable.

Existing relevant code:

- `config/models.yaml`
- `src/omni_tts_core/provider_registry.py`
- `src/omni_tts_core/engines/base.py`
- `src/omni_tts_core/remote/endpoint.py`
- `src/omni_tts_core/engines/higgs_remote_engine.py`
- `src/omni_tts_core/remote/higgs_sglang.py`
- `src/omni_tts_core/generation_concurrency.py`
- `src/omni_tts_core/runtime_status.py`
- `src/omni_tts_core/ui_presenters/settings_state.py`
- `src/omni_tts_ui_qt/pages/higgs_remote_section.py`
- `src/omni_tts_ui_qt/pages/settings_panel.py`
- tests around remote endpoints and concurrency:
  - `tests/test_higgs_remote.py`
  - `tests/test_generation_concurrency.py`
  - `tests/test_control_policy.py`
  - related endpoint/capability tests

The project already has a functioning remote TTS path for:

- model: `higgs_tts3_remote`
- provider: `higgs_remote`
- HTTP speech route
- endpoint health checking
- remote generation
- reference audio encoded and sent to remote
- request timeout/retry
- per-endpoint concurrency
- UI settings for endpoint URL

This is the architectural precedent.

## 4. Existing engines relevant to Colab

### VieNeu v3 Turbo

Current catalog includes:
- model ID: `vieneu_v3_turbo`
- HF repo: `pnnbao-ump/VieNeu-TTS-v3-Turbo`
- CPU path: ONNX FP32
- GPU path: PyTorch/CUDA
- approximately 5 GB VRAM catalog estimate
- fixed presets and voice-profile cloning
- long-form/batch use is a strong target

This is the first engine to support through the Colab worker.

### ZeroTTS

Current ZeroTTS integration is CPU oriented:
- ONNX
- GGUF F32
- GGUF Q8_0
- GGUF Q4_0
- streaming and long-form preprocessing

Do NOT prioritize ZeroTTS for Colab GPU V1. Keep it local CPU.

### OmniVoice

The project already has multiple OmniVoice entries including Vietnamese fine-tunes and base model.

Add later after the worker protocol is proven with VieNeu.

### Higgs TTS 3

Current project has:
- model ID: `higgs_tts3_remote`
- provider: `higgs_remote`
- model repo: `bosonai/higgs-audio-v3-tts-4b`
- remote HTTP architecture already implemented

Do not break this path. Eventually the generic worker architecture should be able to represent Higgs, but Higgs V1 remote behavior must remain compatible.

## 5. Desired target architecture

Separate these concepts:

### Model
Examples:
- VieNeu v3 Turbo
- OmniVoice Vietnamese
- Higgs TTS 3
- ZeroTTS

### Execution target
Examples:
- local_cpu
- local_gpu
- remote_gpu
- colab_worker

### Worker
Examples:
- COLAB-PRO-01
- COLAB-PRO-02
- RUNPOD-A40
- LOCAL-1080TI

The model should not own a Google account.

The worker should not own TTS-specific UI controls that already belong to the model/provider.

Preferred conceptual flow:

```
Studio Job
   -> choose model
   -> choose execution target
   -> resolve compatible worker
   -> validate worker capability
   -> submit
   -> stream/poll progress
   -> retrieve output
   -> existing merge/SRT/history pipeline
```

## 6. V1 scope

Build the smallest real vertical slice:

### Desktop side

Add a remote worker registry capable of:
- adding/registering a worker;
- pair-code flow or equivalent short-lived pairing;
- heartbeat;
- online/offline state;
- worker metadata;
- supported engine/model capabilities;
- endpoint refresh when a Colab tunnel changes;
- remove/forget worker;
- manual health check.

Add a minimal UI:
- Remote Workers / Compute Workers page or section;
- worker name;
- status;
- GPU;
- engine;
- endpoint health;
- last seen;
- pair action;
- forget action.

Add execution routing for:
- `vieneu_v3_turbo`
- target `colab_worker`

Preserve existing local VieNeu paths.

### Colab side

Create one canonical notebook, preferably generated from source rather than maintained as many divergent notebooks.

Suggested filename:
- `colab/Colin-TTS-Colab-Worker.ipynb`

The notebook should expose only a small configuration surface, e.g.:
- worker label;
- pair code or registration token;
- engine selection for V1 = VieNeu;
- optional model cache location;
- optional tunnel mode.

Then Run All should:
1. detect GPU;
2. print GPU/VRAM;
3. clone or update pinned project/worker code;
4. install only required dependencies;
5. restore/download model cache;
6. start the worker API;
7. establish a temporary reachable endpoint;
8. register/heartbeat with the desktop-side registry;
9. show READY with worker ID, GPU, model and endpoint state;
10. expose a clean STOP procedure.

Do not require the user to edit long commands.

## 7. Worker protocol

Do not couple the protocol to Colab.

Name it generically, e.g. `ComputeWorker` or `RemoteTtsWorker`.

Minimum endpoints/capabilities should cover:

- `GET /health`
- `GET /capabilities`
- `POST /v1/tts/jobs`
- `GET /v1/tts/jobs/{id}`
- `POST /v1/tts/jobs/{id}/cancel`
- result download endpoint or a response contract that returns completed artifacts

If existing `/v1/audio/speech` compatibility can be reused safely, preserve it as an adapter, but do not force all future worker jobs into Higgs-specific request fields.

Capabilities should identify:
- protocol version;
- worker ID;
- engine IDs;
- model IDs;
- GPU name;
- VRAM;
- output formats;
- voice profile support;
- supported language metadata;
- max concurrency;
- batch support;
- streaming support if applicable.

## 8. Pairing / registry

Preferred UX:

Desktop:
```
Add Colab Worker
Pair code: N7K4-92Q
Waiting...
```

Notebook:
```
PAIR_CODE = "N7K4-92Q"
```

After Run All:
```
Connected
Worker: COLAB-PRO-02
GPU: NVIDIA L4
Engine: VieNeu v3 Turbo
Status: Ready
```

Implementation can use a small registry service if needed.

Possible backend:
- existing infrastructure if already appropriate;
- otherwise a tiny Cloudflare Worker + KV style registry.

Do not force the desktop client to know Google identity.

Pair codes should:
- expire;
- be single-use where possible;
- exchange for a worker credential;
- not be reusable as permanent secrets.

For V1 personal use, security can remain lightweight but must not be reckless.

## 9. Model caching

Colab local disk is ephemeral.

Design caching as an optimization, not a requirement.

Support:
- Hugging Face direct download;
- optional persistent user cache;
- model revision pinning.

Avoid assuming Google Drive is always mounted.

If persistent cache is added:
- use one archive where practical instead of huge numbers of tiny files;
- validate revision/hash/manifest;
- fall back to normal download when cache is missing or invalid.

Do not commit model weights into the project Git repository.

## 10. Job durability

The desktop app should remain source of truth for submitted work.

For long-form jobs:
- assign stable desktop job ID;
- split/chunk using the existing pipeline where appropriate;
- make chunk results idempotent;
- record completed chunk indexes;
- retry only missing/failed chunks after worker disconnect;
- do not regenerate all finished chunks after Colab runtime loss.

A worker disconnect must yield a recoverable state such as:
- worker_offline
- retryable
- partial_results_available

not generic data loss.

## 11. Compute efficiency

The goal is to spend paid Colab compute only during useful work.

Expected user workflow:
1. start notebook;
2. wait until READY;
3. submit one or many large jobs;
4. complete/export/sync results;
5. stop worker;
6. disconnect/delete the Colab runtime.

Add user-visible guidance:
- idle worker = paid compute may still be consumed;
- close browser tab is not equivalent to guaranteed runtime termination;
- provide a clear Stop Worker action;
- notebook final cell should explain disconnect/delete runtime.

Optional later feature:
- idle warning;
- automatic worker self-stop timer;
- do NOT attempt automated Google account logout.

## 12. Multi-account behavior

Do not pool Google accounts directly.

Pool workers.

Example:
```
COLAB-PRO-01 online L4  VieNeu
COLAB-PRO-02 offline
COLAB-PRO-03 online L4  VieNeu
```

Scheduling modes later:
- manual worker selection;
- least-busy compatible worker;
- split batch across multiple online workers.

V1 should prefer explicit/manual selection for predictability.

Do not implement automatic quota rotation between Google accounts in V1.

## 13. Backward compatibility

Must preserve:
- local CPU engines;
- local GPU engines;
- existing Higgs Remote;
- existing generation history;
- SRT/export/merge pipeline;
- voice profiles;
- current model catalog behavior;
- MCP behavior unless explicitly expanded.

No breaking migration of user settings without defaults/fallback.

## 14. Testing expectations

At minimum add tests for:
- worker capability schema;
- worker online/offline/heartbeat;
- pair-code lifecycle;
- endpoint URL refresh;
- VieNeu execution target routing;
- local VieNeu regression;
- remote Higgs regression;
- job retry after simulated worker disconnect;
- duplicate chunk protection/idempotency;
- UI state serialization;
- concurrency isolation per worker.

Create a real smoke test against a local fake worker before requiring Colab.

Then run a real Colab smoke test:
- L4 if available;
- VieNeu model loads;
- one Vietnamese sample;
- one English/code-switch sample;
- one voice-profile sample;
- one multi-chunk batch;
- force disconnect and resume missing chunks.

Record measured:
- setup time;
- model restore/download time;
- GPU/VRAM;
- generation wall time;
- audio duration;
- RTF;
- endpoint overhead;
- failure/retry behavior.

## 15. Implementation discipline for Codex

Before editing:
1. inspect git status;
2. do not reset unrelated user changes;
3. read all files that will be patched;
4. identify existing schema and persistence patterns;
5. use existing abstractions before introducing new ones.

During implementation:
- keep files reasonably sized;
- isolate worker protocol from provider-specific logic;
- do not bake Google account names into source;
- do not hardcode tunnel URLs;
- do not hardcode personal tokens;
- keep secrets out of Git;
- add tests with each phase.

After each meaningful phase:
- run focused tests;
- run broader regression tests before completion;
- update docs.

Do not commit/push unless the user explicitly asks.

## 16. Definition of done for V1

V1 is done when:

1. A user opens one canonical Colab notebook from Google Account A.
2. Selects an L4 or another supported GPU.
3. Runs all.
4. VieNeu worker becomes READY without manual command-by-command setup.
5. Colin TTS Studio displays that worker automatically after pairing.
6. User chooses VieNeu v3 Turbo + Colab Worker.
7. A multi-chunk TTS job completes.
8. Existing output/history/SRT behavior remains intact.
9. If the runtime dies, completed chunks are not lost and remaining chunks can resume.
10. User can stop the worker and is clearly told to disconnect/delete the Colab runtime.
11. The same notebook works from Google Account B without source changes.
12. No Google password/session secret is stored in Colin TTS Studio.

## 17. Explicit non-goals for V1

Do not spend V1 time on:
- automatic Google login or account switching;
- reading Colab CCU balance programmatically unless an official stable API is found;
- automatic quota rotation;
- ZeroTTS GPU;
- 24/7 Colab serving;
- complex distributed scheduling;
- Kubernetes;
- billing dashboard;
- fully automatic multi-cloud orchestration.

Prove one clean VieNeu Colab worker first.
