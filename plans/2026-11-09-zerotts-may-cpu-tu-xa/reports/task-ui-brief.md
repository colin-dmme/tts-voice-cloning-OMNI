# Task 1 — CPU remote UI and request contract

Read this first. Implement the common CPU machine choice for ZeroTTS Official, Piper ONNX and VieNeu v3 in the current Studio. No implementation subagents. You are not alone in the codebase: preserve all other edits, especially narrative pacing and the pre-existing Colab foundation.

## Ownership

Own only:
- src/omni_tts_shared/schemas.py
- src/omni_tts_core/engines/base.py
- src/omni_tts_core/ui_presenters/settings_state.py
- src/omni_tts_core/ui_presenters/control_policy.py
- src/omni_tts_core/runtime_devices.py
- src/omni_tts_core/user_state.py
- src/omni_tts_ui_qt/pages/settings_panel.py
- src/colin_colab_remote/ui/remote_compute_section.py
- src/colin_remote_compute/ui/pc_devices_dialog.py (new)
- src/colin_studio_tts_mcp/contracts.py
- Focused tests for these contracts/UI; update existing matching tests only as necessary.

Root owns service.py, provider_registry.py, engines/routing, the rest of colin_colab_remote/colin_remote_compute, broker models/client, and entire compute-service repository. Coordinate instead of editing those.

## Frozen interfaces

Shared schemas add `RemoteComputeTarget` with `kind: Literal['existing_worker','managed_colab']`, `worker_profile_id: str=''` (max128), `backend: Literal['cpu','cuda']='cpu'`; extra fields forbidden. Add `remote_compute: RemoteComputeTarget|None=None` to GenerateSpeechRequest and TtsEngineRequest, and MCP generation contract. Existing enum `runtime_target=auto|cpu|cuda|remote` unchanged. A nonempty remote_compute requires runtime_target=remote. Existing-worker path currently CPU only, reject unsupported combinations clearly.

GenerationSettings uses three backward-compatible flat fields: `remote_execution_kind: str=''`, `remote_worker_profile_id: str=''`, `remote_execution_backend: str=''`. to_request creates RemoteComputeTarget only when kind nonblank. Defaults, preferences, user-state allowlists, history and current_settings restore all three. Root's dispatcher will resolve these fields; never store credentials here.

UI-only combo key `remote_cpu` maps to canonical runtime_target=remote + existing_worker/cpu, never into normalize_runtime_target (unknown keys currently fall back to auto). Restore maps fields back to this UI key. Auto and local CPU/CUDA retain their behavior. Legacy remote key remains old Colab choice.

Show `CPU máy khác` for ZeroTTS Official, Piper ONNX models, VieNeu v3 Turbo only (not all VieNeu/GGUF and not Higgs). It must be visible even if model/worker missing locally. Add common worker selection; do not derive remote readiness from local GPU/model installation. Piper needs same remote controls as Zero/V3. Current Higgs remote-only endpoint remains separate; reject/ignore no CPU target silently.

Broker WorkerProfile gets optional `worker_kind='generic'|'google_colab'|'remote_pc'` default generic (root supplies). PC profiles should be filtered by kind or pc- prefix compat. Preserve remote profile selection and changed signal. Existing global selection is legacy; explicit remote_worker_profile_id is actual new CPU target and must survive round-trip.

Root adds these BrokerClient methods (dict responses, authenticated admin on main PC):
- inspect_pc_pairing(user_code) -> {pairing_id,worker_id,display_name,runtime:{platform,cpu,ram_mb},models:[ModelCapability],expires_at}
- approve_pc_pairing(user_code,preview) -> {status:'approved',worker_id,display_name,...}; approval gets exact preview pairing_id/worker_id.
- list_pc_devices() -> [{worker_id,display_name,allowed_models:[str],desired_state:'running'|'paused'|'stopped',observed_state,last_seen_at,...}]
- control_pc_device(worker_id,action) with action='resume'|'pause'|'stop' -> desired/observed state dict
- revoke_pc_device(worker_id) -> {status:'revoked',worker_id}

Implement PC devices dialog (pair code inspect, explicit approve, list/status, pause/resume/stop/revoke) using FunctionTask off UI thread. Reuse pairing_client(profile) for admin BrokerClient. After approval upsert WorkerProfile(profile_id=worker_id,worker_id=worker_id,label=display_name,broker_url/auth settings copied from main connection,worker_kind='remote_pc'). No master key transmission. No actual external calls/permissions during tests.

## Test / acceptance

Write meaningful failing tests first, record RED, implement GREEN. Tests cover remote target valid/invalid, no target legacy, settings/MCP serialization, combo round-trip and explicit profile, Piper CPU choice with no local install, Higgs unchanged, no UI key accidentally normalize to auto. Run focused tests while iterating. Root runs final integrated full suites once concurrent edits settle. Do not commit entire previously dirty files; report changed files and any pre-existing unrelated hunks. Root will handle scoped final commit/release.

Report to `plans/2026-11-09-zerotts-may-cpu-tu-xa/reports/task-ui-report.md`, include RED/GREEN commands/results, files, integration concerns, self-review. Return under15 lines. Do not spawn agents. Ask root about interface ambiguity, not the user.
