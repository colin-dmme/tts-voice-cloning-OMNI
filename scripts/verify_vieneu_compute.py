"""Verify real VieNeu v3 preset and clone audio through the configured broker.

Runs a temporary worker on this PC, not on Google Colab. Never changes the
Studio's saved worker selection or Google profiles. Outputs are kept for review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    if args.output_dir.exists():
        raise SystemExit("Output directory already exists; choose a new directory.")
    sys.path.insert(0, str(args.service_root / "src"))

    import numpy as np
    import soundfile as sf
    from colin_compute_service.protocol import ModelCapability, RuntimeInfo, WorkerCapabilities
    from colin_compute_service.vieneu import VieneuResidentHandler
    from colin_compute_service.worker import ComputeWorker, WorkerHttpClient
    from omni_tts_core.engines.base import TtsEngineRequest
    from omni_tts_core.engines.vieneu_routing_engine import VieneuRoutingEngine
    from omni_tts_core.model_registry import ModelRegistry
    from omni_tts_core.remote_compute.client import BrokerClient
    from omni_tts_core.remote_compute.failover import RemoteComputeCoordinator
    from omni_tts_core.remote_compute.models import BrokerConnectionOptions, WorkerProfile, WorkerSelectionSettings
    from omni_tts_core.remote_compute.profiles import WorkerProfileDocument, WorkerProfileStore
    from omni_tts_core.storage_paths import hf_cache_env

    os.environ.update(hf_cache_env())
    document = WorkerProfileStore(STUDIO_ROOT / "config/remote_compute_workers.json").load()
    original = next(profile for profile in document.profiles if profile.enabled)
    if original.auth_token_file is None:
        raise SystemExit("This check requires the existing local broker token file.")
    token = original.auth_token_file.read_text(encoding="utf-8").strip()
    spec = ModelRegistry().get("vieneu_v3_turbo")
    worker_id = f"vieneu-verification-{uuid.uuid4().hex[:10]}"
    client = WorkerHttpClient(original.broker_url, token, timeout_seconds=30)
    cache = args.output_dir / "reference-cache"
    handler = VieneuResidentHandler(
        STUDIO_ROOT / "engines/vieneu_v3_worker/.venv/Scripts/python.exe",
        STUDIO_ROOT / "engines/vieneu_v3_worker/synthesize.py", device=args.device,
        reference_loader=lambda asset_id: client.fetch_reference(asset_id, cache),
    )
    worker = ComputeWorker(client, WorkerCapabilities(
        worker_id=worker_id, display_name="VieNeu real audio check (PC, temporary)", worker_type="verification",
        runtime=RuntimeInfo(platform=sys.platform),
        models=(ModelCapability(
            model_id=spec.model_id, provider_id="vieneu", execution_backend=args.device,
            sample_rate=48000, supports_profile_clone=True, supports_batch=True, output_formats=("wav", "zip"),
        ),),
    ), handler)
    stop = threading.Event()
    failures = []
    thread = None
    args.output_dir.mkdir(parents=True)
    try:
        print(f"Loading VieNeu v3 3.6.4 on this PC ({args.device})...", flush=True)
        handler.warmup()
        worker.register()

        def run_worker():
            try:
                while not stop.is_set():
                    if not worker.run_once():
                        stop.wait(0.5)
            except Exception as error:
                failures.append(str(error))

        thread = threading.Thread(target=run_worker, daemon=True)
        thread.start()

        class TimedClient(BrokerClient):
            def wait_for_terminal(self, job_id, **kwargs):
                return super().wait_for_terminal(job_id, timeout_seconds=600, **kwargs)

        def coordinator(config, *, confirm_switch, status_callback):
            return RemoteComputeCoordinator(config, client_factory=lambda profile: TimedClient(BrokerConnectionOptions(
                base_url=profile.broker_url, auth_token_file=profile.auth_token_file,
                request_timeout_seconds=30, max_retries=0,
            )), confirm_switch=confirm_switch, status_callback=status_callback)

        outputs = []
        with tempfile.TemporaryDirectory(prefix="vieneu-verify-") as temporary:
            store = WorkerProfileStore(Path(temporary) / "workers.json")
            store.save(WorkerProfileDocument(profiles=[WorkerProfile(
                profile_id=worker_id, worker_id=worker_id, label="Temporary PC verification",
                broker_url=original.broker_url, auth_token_file=original.auth_token_file,
            )], selection=WorkerSelectionSettings(selected_profile_id=worker_id)))
            engine = VieneuRoutingEngine(spec, profile_store=store, coordinator_factory=coordinator)
            try:
                def generate(label, texts, reference=None):
                    results = engine.generate_batch([TtsEngineRequest(
                        text=text, language="vi", reference_audio_path=reference, reference_text=None,
                        speaker_id="Ngọc Huyền" if reference is None else None,
                        speed=1.0, pitch_shift=0.0, runtime_target="remote",
                        status_callback=lambda message: print(message, flush=True),
                    ) for text in texts])
                    paths = []
                    for index, result in enumerate(results, start=1):
                        path = args.output_dir / f"{label}-{index:02d}.wav"
                        sf.write(path, result.audio, result.sample_rate, subtype="PCM_16")
                        if result.sample_rate != 48000 or len(result.audio) < 4800 or not np.isfinite(result.audio).all() or np.max(np.abs(result.audio)) < 0.001:
                            raise RuntimeError("Invalid or silent VieNeu output")
                        outputs.append({"path": str(path.resolve()), "sample_rate": result.sample_rate,
                                        "duration_seconds": len(result.audio) / result.sample_rate,
                                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
                        paths.append(path)
                    return paths

                preset = generate("ngoc-huyen-v3", [
                    "Xin chào. Đây là giọng Ngọc Huyền trong VieNeu phiên bản ba.",
                    "Mẫu giọng dựng sẵn đang được kiểm tra qua dịch vụ điện toán từ xa.",
                ])
                generate("clone-v3", [
                    "Xin chào. Tôi đang kiểm tra tính năng clone giọng từ audio mẫu.",
                    "Văn bản này khác với lời nói trong bản ghi tham chiếu.",
                ], preset[0])
                # A second clone request exercises the same content-addressed reference and resident model.
                generate("clone-cache-v3", ["Giọng tham chiếu được tái sử dụng cho yêu cầu tiếp theo."], preset[0])
            finally:
                engine.close()
        report = {"broker_url": original.broker_url, "worker_id": worker_id,
                  "worker_location": "PC, not Google Colab", "execution_backend": args.device,
                  "sdk_version": "3.6.4", "preset": "Ngọc Huyền", "outputs": outputs}
        (args.output_dir / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False), flush=True)
    finally:
        stop.set()
        if thread is not None:
            thread.join(timeout=5)
        handler.close()
    if failures:
        raise RuntimeError("; ".join(failures))


if __name__ == "__main__":
    main()
