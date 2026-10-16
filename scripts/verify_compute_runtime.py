"""Run real ZeroTTS inference through the public broker with a temporary PC worker."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
import uuid
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STUDIO_ROOT / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-root", type=Path, default=Path("D:/_coder/colin-tts-compute-service"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Output already exists. Select a new filename.")
    sys.path.insert(0, str(args.service_root / "src"))

    import soundfile as sf
    from colin_compute_service.protocol import ModelCapability, RuntimeInfo, WorkerCapabilities
    from colin_compute_service.worker import ComputeWorker, WorkerHttpClient, ZeroTtsResidentHandler
    from omni_tts_core.engines.base import TtsEngineRequest
    from omni_tts_core.engines.zerotts_routing_engine import ZeroTtsRoutingEngine
    from omni_tts_core.model_registry import ModelRegistry
    from omni_tts_core.remote_compute.client import BrokerClient
    from omni_tts_core.remote_compute.failover import RemoteComputeCoordinator
    from omni_tts_core.remote_compute.models import BrokerConnectionOptions, WorkerProfile, WorkerSelectionSettings
    from omni_tts_core.remote_compute.profiles import WorkerProfileDocument, WorkerProfileStore

    document = WorkerProfileStore(STUDIO_ROOT / "config/remote_compute_workers.json").load()
    original = next(p for p in document.profiles if p.enabled)
    if original.auth_token_file is None:
        raise SystemExit("A local broker token file is required for this check.")
    token = original.auth_token_file.read_text(encoding="utf-8").strip()
    spec = ModelRegistry().get("zerotts_202m_official")
    worker_id = f"recovery-check-{uuid.uuid4().hex[:10]}"
    handler = ZeroTtsResidentHandler(
        STUDIO_ROOT / "engines/zerotts_worker/.venv/Scripts/python.exe",
        STUDIO_ROOT / "engines/zerotts_worker/synthesize.py",
        spec.local_path,
    )
    worker = ComputeWorker(
        WorkerHttpClient(original.broker_url, token, timeout_seconds=20.0),
        WorkerCapabilities(
            worker_id=worker_id,
            display_name="Recovery verification on PC (temporary)",
            worker_type="recovery_diagnostic",
            runtime=RuntimeInfo(platform=sys.platform),
            models=(ModelCapability(model_id=spec.model_id, provider_id="zerotts", execution_backend="cpu", sample_rate=48000),),
        ),
        handler,
    )
    worker.register()
    stop = threading.Event()
    failures: list[str] = []

    def run_worker() -> None:
        try:
            while not stop.is_set():
                if worker.run_once():
                    return
                stop.wait(0.5)
        except Exception as error:
            failures.append(str(error))

    thread = threading.Thread(target=run_worker, daemon=True)
    thread.start()

    class TimedClient(BrokerClient):
        def wait_for_terminal(self, job_id, **kwargs):
            return super().wait_for_terminal(job_id, timeout_seconds=180.0, **kwargs)

    def coordinator(config, *, confirm_switch, status_callback):
        return RemoteComputeCoordinator(
            config,
            client_factory=lambda profile: TimedClient(BrokerConnectionOptions(
                base_url=profile.broker_url,
                auth_token_file=profile.auth_token_file,
                request_timeout_seconds=20.0,
                max_retries=0,
            )),
            confirm_switch=confirm_switch,
            status_callback=status_callback,
        )

    try:
        with tempfile.TemporaryDirectory(prefix="colin-recovery-") as temporary:
            store = WorkerProfileStore(Path(temporary) / "profiles.json")
            store.save(WorkerProfileDocument(
                profiles=[WorkerProfile(
                    profile_id=worker_id,
                    worker_id=worker_id,
                    label="Recovery verification on PC",
                    broker_url=original.broker_url,
                    auth_token_file=original.auth_token_file,
                )],
                selection=WorkerSelectionSettings(selected_profile_id=worker_id),
            ))
            engine = ZeroTtsRoutingEngine(spec, profile_store=store, coordinator_factory=coordinator)
            try:
                result = engine.generate(TtsEngineRequest(
                    text="Xin chào. Colin TTS đã được khôi phục và sẵn sàng sử dụng.",
                    language="vi",
                    reference_audio_path=None,
                    reference_text=None,
                    speaker_id="maichi",
                    speed=1.0,
                    pitch_shift=0.0,
                    runtime_target="remote",
                    provider_options={"seed": 42},
                    status_callback=lambda message: print(message, flush=True),
                ))
            finally:
                engine.close()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            sf.write(args.output, result.audio, result.sample_rate, subtype="PCM_16")
            info = sf.info(args.output)
            if info.frames == 0 or info.samplerate != 48000:
                raise RuntimeError("Invalid output audio.")
            print(json.dumps({
                "output": str(args.output.resolve()),
                "sample_rate": info.samplerate,
                "duration_seconds": info.duration,
                "worker_id": worker_id,
                "worker_location": "PC, not Google Colab",
            }, ensure_ascii=False), flush=True)
    finally:
        stop.set()
        thread.join(timeout=5.0)
        handler.close()
    if failures:
        raise RuntimeError("; ".join(failures))


if __name__ == "__main__":
    main()
