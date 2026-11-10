"""Own exactly one Google runtime and pair its worker through the existing broker."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from uuid import uuid4
from urllib.parse import urlsplit

from omni_tts_shared.errors import GenerationCancelled, GenerationError

from .broker.client import BrokerClient
from .broker.local_broker import LocalBrokerManager
from .broker.models import BrokerConnectionOptions, WorkerProfile, WorkerSelectionSettings
from .broker.profiles import WorkerProfileDocument, WorkerProfileStore
from .settings import ColabSettings
from .store import ColabStore


def output_json(result: dict) -> dict:
    value = result.get("value")
    if isinstance(value, dict):
        return value
    stdout = result.get("stdout", "")
    if isinstance(stdout, list):
        stdout = "".join(str(item) for item in stdout)
    for line in reversed(str(stdout).splitlines()):
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    raise GenerationError("Colab chưa trả thông tin khởi động hợp lệ.")


class ColabLifecycle:
    def __init__(self, store: ColabStore, settings: ColabSettings, provider, profiles: WorkerProfileStore):
        self.store, self.settings, self.provider = store, settings, provider
        source = next((p for p in profiles.load().profiles if p.profile_id == settings.account_id and p.enabled), None)
        if source is None:
            raise GenerationError("Chưa cấu hình broker cho tài khoản Colab đã chọn.")
        parsed = urlsplit(source.broker_url)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise GenerationError("Colab tự động cần địa chỉ broker HTTPS hợp lệ.")
        self.profile = source.model_copy(update={"profile_id": "managed-" + settings.account_id,
                                                "worker_id": "managed-" + settings.account_id,
                                                "label": "Colab tự động " + settings.account_id[-1]})
        self.broker = BrokerClient(BrokerConnectionOptions(base_url=source.broker_url, auth_env=source.auth_env,
                                                          auth_token_file=source.auth_token_file, max_retries=0,
                                                          request_timeout_seconds=30))

    @property
    def document(self):
        return WorkerProfileDocument(profiles=[self.profile], selection=WorkerSelectionSettings(
            selected_profile_id=self.profile.profile_id, switch_policy="selected_only"))

    def record(self) -> dict:
        return self.store.state("runtime", {})

    def expired(self) -> bool:
        record = self.record()
        return bool(record and time.time() >= record.get("deadline", 0))

    def _save(self, record: dict, phase: str) -> None:
        record["phase"] = phase
        self.store.set_state("runtime", record)

    def _execute(self, code: str, record: dict, operation: str) -> dict:
        ids = record.setdefault("execution_ids", {})
        execution_id = ids.setdefault(operation, str(uuid4()))
        self.store.set_state("runtime", record)
        return self.provider.execute(code, record["session"], execution_id)

    def ensure(self, model_id: str, check, message) -> None:
        check()
        model_provider = "vieneu_v3" if model_id == "vieneu_v3_turbo" else "zerotts"
        device = "cuda" if model_provider == "vieneu_v3" else "cpu"
        record = self.record()
        if record and (record.get("model_id") != model_id or record.get("account_id") != self.settings.account_id or self.expired()):
            self.release()
            record = {}
        if not record:
            health = LocalBrokerManager().status(check_public=True)
            if not health.local_healthy and self.settings.start_broker:
                message("Bật broker trên PC")
                LocalBrokerManager().start()
            health = self.broker.health()
            if health.get("managed_colab") != "enabled":
                raise GenerationError("Cần cập nhật và khởi động lại compute broker để dùng Colab tự động.")
            subscription = self.provider.get_subscription()
            if subscription.get("tier") not in {"SUBSCRIPTION_TIER_PRO", "SUBSCRIPTION_TIER_PRO_PLUS"}:
                raise GenerationError(
                    "Colab chưa ghi nhận quyền lợi trả phí của tài khoản này. "
                    "Google AI Pro trong kỳ dùng thử không bao gồm quyền lợi Colab. "
                    "Kiểm tra gói và Compute Units trong Colab."
                )
            specs = self.provider.list_runtime_specs()
            spec = self._select_spec(specs, device)
            stamp = time.time()
            record = {"runtime_id": "colin-" + uuid4().hex, "request_id": str(uuid4()),
                      "launch_id": uuid4().hex, "account_id": self.settings.account_id,
                      "worker_id": self.profile.worker_id, "model_id": model_id,
                      "provider": model_provider, "device": device, "spec": spec,
                      "created_at": datetime.now(timezone.utc).isoformat(),
                      "deadline": stamp + self.settings.max_runtime_minutes * 60,
                      "startup_deadline": stamp + self.settings.startup_timeout_seconds,
                      "execution_ids": {}}
            self._save(record, "allocating")
        if record["phase"] == "release_pending":
            self.release()
            return self.ensure(model_id, check, message)
        if record["phase"] == "allocating":
            message("Đang cấp runtime Colab")
            check()
            runtime = self.provider.create_runtime(record["runtime_id"], record["request_id"], record["spec"])
            record["name"] = runtime.get("name", "runtimes/" + record["runtime_id"])
            record["session"] = record["name"] + "/sessions/colin-worker"
            self._save(record, "session")
        if record["phase"] == "session":
            check()
            self.provider.create_session(record["name"], "colin-worker")
            self._save(record, "pairing")
        if record["phase"] == "pairing":
            message("Ghép worker với runtime vừa cấp")
            # The source is read in the authenticated, app-owned kernel. Its private
            # device code and worker credential stay in that kernel's module RAM.
            args = json.dumps([self.profile.broker_url, self.profile.worker_id, model_provider, device, record["launch_id"]])
            code = (
                "import json, types, urllib.request\n"
                "if '_colin_managed' not in globals():\n"
                "    class _NoColinRedirect(urllib.request.HTTPRedirectHandler):\n"
                "        def redirect_request(self, *args, **kwargs): raise RuntimeError('bootstrap redirect')\n"
                f"    _src = urllib.request.build_opener(_NoColinRedirect()).open({self.profile.broker_url + '/colab/managed-bootstrap.py'!r}, timeout=30).read(131073)\n"
                "    if len(_src) > 131072: raise RuntimeError('bootstrap size')\n"
                "    _colin_module = types.ModuleType('colin_managed_bootstrap')\n"
                "    exec(compile(_src, '<colin-managed>', 'exec'), _colin_module.__dict__)\n"
                "    _colin_managed = _colin_module\n"
                f"print(json.dumps(_colin_managed.begin(*json.loads({args!r}))))"
            )
            begin = output_json(self._execute(code, record, "begin"))
            if (begin.get("worker_id"), begin.get("launch_id")) != (self.profile.worker_id, record["launch_id"]):
                raise GenerationError("Phiên khởi động Colab không khớp worker đã cấp.")
            approval = self.broker.get_pairing_launch(record["launch_id"])
            if approval.get("status") != "approved":
                preview = self.broker.inspect_pairing(begin["user_code"])
                if (preview.worker_id, preview.provider, preview.device, preview.launch_id) != (
                        self.profile.worker_id, model_provider, device, record["launch_id"]):
                    raise GenerationError("Broker từ chối phiên Colab không khớp lần khởi động.")
                try:
                    self.broker.approve_pairing(begin["user_code"], preview)
                except GenerationError:
                    approval = self.broker.get_pairing_launch(record["launch_id"])
                else:
                    approval = self.broker.get_pairing_launch(record["launch_id"])
            expected = (self.profile.worker_id, model_provider, device, record["launch_id"])
            if approval.get("status") != "approved" or tuple(approval.get(k) for k in ("worker_id", "provider", "device", "launch_id")) != expected:
                raise GenerationError("Chưa xác nhận được quyền worker cho runtime này.")
            self._save(record, "launching")
        if record["phase"] == "launching":
            args = json.dumps([self.profile.broker_url, self.profile.worker_id, model_provider, device, record["launch_id"]])
            output_json(self._execute(f"print(json.dumps(_colin_managed.launch(*json.loads({args!r}))))", record, "launch"))
            self._save(record, "warming")
        while True:
            check()
            if time.time() >= record["deadline"]:
                raise GenerationError("Đã đến hạn sử dụng runtime. Tiến độ được giữ để tiếp tục.")
            workers = self.broker.list_workers()
            for worker in workers:
                caps = worker.capabilities
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(worker.last_seen_at)).total_seconds()
                if (caps.worker_id == self.profile.worker_id and caps.launch_id == record["launch_id"] and 0 <= age < 120
                        and any(m.model_id == model_id and m.execution_backend == device for m in caps.models)):
                    self._save(record, "ready")
                    return
            if record["phase"] == "ready":
                self.release()
                return self.ensure(model_id, check, message)
            if time.time() >= record["startup_deadline"]:
                raise GenerationError("Hết thời gian cài model Colab. Có thể xem tiến độ và thử lại.")
            status = output_json(self.provider.execute(
                f"print(json.dumps(_colin_managed.managed_status({record['launch_id']!r})))", record["session"], str(uuid4())))
            if status.get("status") in {"failed", "stopped", "error", "exited"}:
                raise GenerationError("Worker Colab dừng trong lúc cài model. Kiểm tra phiên Colab rồi tiếp tục.")
            message("Đang tải môi trường và nạp model Colab")
            time.sleep(2)

    def _select_spec(self, specs: list[dict], device: str) -> dict:
        variant = "VARIANT_GPU" if device == "cuda" else "VARIANT_CPU"
        accelerator = self.settings.accelerator if device == "cuda" else "NONE"
        for item in specs:
            key = item.get("key", item.get("runtimeSpec", item))
            if item.get("eligible") is True and key.get("variant") == variant and key.get("accelerator") == accelerator and key.get("shape") == "SHAPE_STANDARD":
                return {k: key[k] for k in ("variant", "accelerator", "shape")}
        raise GenerationError("Tài khoản chưa được cấp quyền yêu cầu cấu hình Colab đã chọn.")

    def release(self) -> None:
        record = self.record()
        if not record:
            return
        if record["phase"] == "allocating":
            # Resolve an uncertain create with the original idempotent request
            # before deleting, so an operation completing late cannot orphan a VM.
            runtime = self.provider.create_runtime(record["runtime_id"], record["request_id"], record["spec"])
            record["name"] = runtime.get("name", "runtimes/" + record["runtime_id"])
        self._save(record, "release_pending")
        # Ownership is persisted before allocation. Never enumerate and delete
        # someone else's interactive runtimes to make room.
        name = record.get("name", "runtimes/" + record["runtime_id"])
        self.provider.delete_runtime(name)
        self.broker.revoke_pairing(record["worker_id"])
        self.store.set_state("runtime", {})
