"""Windows broker lifecycle, separate from remote worker/revocation controls."""
from __future__ import annotations

import json
import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from contextlib import contextmanager
from pathlib import Path
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from filelock import FileLock, Timeout


TASK_NAME = "Colin TTS Compute Broker"
DEFAULT_RUNTIME = Path("C:/Coder/colin-tts-compute-runtime")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise OSError("Broker không được chuyển hướng yêu cầu quản lý")


@dataclass(frozen=True)
class LocalBrokerStatus:
    task_state: str = "Unknown"
    auto_start: bool = False
    local_healthy: bool = False
    desired_running: bool = True
    local_port: int | None = None
    public_url: str = ""
    public_healthy: bool | None = None
    running_jobs: int | None = None
    queued_jobs: int | None = None
    hidden_launcher: bool = False


class LocalBrokerManager:
    def __init__(self, data_dir: Path = DEFAULT_RUNTIME):
        self.data_dir = data_dir

    def _task(self, action: str = "status") -> dict:
        if sys.platform != "win32":
            raise RuntimeError("Điều khiển broker nền chỉ hỗ trợ Windows")
        actions = {
            "status": "",
            "start": f"Enable-ScheduledTask -TaskName '{TASK_NAME}' | Out-Null; Start-ScheduledTask -TaskName '{TASK_NAME}';",
            "disable": f"Disable-ScheduledTask -TaskName '{TASK_NAME}' | Out-Null;",
            "stop": f"Stop-ScheduledTask -TaskName '{TASK_NAME}';",
        }
        if action not in actions:
            raise ValueError("Thao tác broker không hợp lệ")
        script = (
            "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
            + actions[action] + f"$t=Get-ScheduledTask -TaskName '{TASK_NAME}'; "
            "[pscustomobject]@{state=[string]$t.State;enabled=[bool]$t.Settings.Enabled;"
            "hidden_launcher=([System.IO.Path]::GetFileName($t.Actions[0].Execute) -ieq 'pythonw.exe')} | ConvertTo-Json -Compress"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
            stdin=subprocess.DEVNULL, capture_output=True, encoding="utf-8", errors="replace",
            creationflags=0x08000000, timeout=20,
        )
        if result.returncode != 0:
            raise RuntimeError("Không điều khiển được task Colin TTS Compute Broker. Kiểm tra task đã cài và quyền Windows.")
        try:
            return json.loads(result.stdout.lstrip("\ufeff"))
        except (ValueError, AttributeError) as error:
            raise RuntimeError("Windows trả trạng thái task không hợp lệ") from error

    def _control(self, desired: str):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        destination = self.data_dir / "background-control.json"
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps({"version": 1, "desired_state": desired}), encoding="utf-8")
        os.replace(temporary, destination)

    @contextmanager
    def _operation(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        lock = FileLock(self.data_dir / "background-operation.lock")
        try:
            lock.acquire(timeout=0)
        except Timeout as error:
            raise RuntimeError("Một cửa sổ khác đang bật/tắt broker. Chờ hoàn tất rồi làm mới trạng thái.") from error
        try:
            yield
        finally:
            lock.release()

    @staticmethod
    def _read(path: Path) -> dict:
        try:
            result = json.loads(path.read_text(encoding="utf-8-sig"))
            return result if isinstance(result, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _health(url: str) -> bool:
        try:
            request = Request(url + "/health", headers={"User-Agent": "Colin-TTS-Studio/0.5"})
            # Local requests must never be sent through an external system proxy.
            opener = build_opener(ProxyHandler({})) if url.startswith("http://127.0.0.1:") else build_opener()
            with opener.open(request, timeout=3) as response:
                payload = json.loads(response.read(8192))
            return payload.get("status") == "ok" and payload.get("service") == "colin-tts-compute-broker"
        except (OSError, ValueError):
            return False

    def status(self, *, check_public: bool = False) -> LocalBrokerStatus:
        task = self._task()
        runtime = self._read(self.data_dir / "runtime.json")
        control_path = self.data_dir / "background-control.json"
        desired = not control_path.exists() or self._read(control_path).get("desired_state") == "running"
        port = runtime.get("local_port")
        valid_port = type(port) is int and 18787 <= port <= 18849
        healthy = self._health(f"http://127.0.0.1:{port}") if valid_port else False
        public_url = ""
        # Only accept the configured hostname, never an arbitrary URL from a status file.
        configured = self._read(self.data_dir / "background-config.json").get("hostname")
        if configured and configured == runtime.get("hostname") and all(c.isalnum() or c in ".-" for c in configured):
            public_url = "https://" + configured
        counts = {}
        if healthy:
            try:
                token = (self.data_dir / "secrets/broker-token.txt").read_text(encoding="utf-8").strip()
                request = Request(f"http://127.0.0.1:{port}/v1/broker/status", headers={
                    "Authorization": "Bearer " + token, "User-Agent": "Colin-TTS-Studio/0.5",
                })
                with build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=2) as response:
                    counts = json.loads(response.read(8192))
            except (OSError, ValueError):
                pass  # Old brokers may not yet expose the queue counters.
        return LocalBrokerStatus(
            task_state=task.get("state", "Unknown"), auto_start=bool(task.get("enabled")),
            local_healthy=healthy, desired_running=desired, local_port=port if valid_port else None,
            public_url=public_url, public_healthy=self._health(public_url) if check_public and public_url else None,
            running_jobs=counts.get("running_jobs"), queued_jobs=counts.get("queued_jobs"),
            hidden_launcher=bool(task.get("hidden_launcher")),
        )

    def _wait(self, running: bool, timeout: float) -> LocalBrokerStatus:
        deadline = time.monotonic() + timeout
        while True:
            result = self.status()
            if running and result.local_healthy and result.task_state == "Running":
                return result
            if not running and not result.local_healthy and result.task_state != "Running":
                return result
            if time.monotonic() >= deadline:
                raise RuntimeError("Broker chưa xác nhận " + ("đã bật" if running else "đã tắt") + ". Xem log, không tự mở thêm phiên.")
            time.sleep(0.5)

    def start(self) -> LocalBrokerStatus:
        with self._operation():
            self._control("running")
            self._task("start")
            return self._wait(True, 45)

    def stop(self) -> LocalBrokerStatus:
        with self._operation():
            self._control("stopped")
            self._task("disable")
            try:
                return self._wait(False, 18)
            except RuntimeError:
                # Cooperative marker first. Task Scheduler's owned job is the fallback,
                # not broad taskkill /IM or killing an arbitrary PID from a stale JSON file.
                self._task("stop")
                return self._wait(False, 8)


def main():
    from dataclasses import asdict
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("status", "start", "stop"))
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--confirm-stop", action="store_true")
    args = parser.parse_args()
    if args.action == "stop" and not args.confirm_stop:
        parser.error("Dùng giao diện quản lý để xác nhận tắt, hoặc thêm --confirm-stop khi đã xác nhận")
    manager = LocalBrokerManager(args.data_dir)
    try:
        result = getattr(manager, {"status": "status", "start": "start", "stop": "stop"}[args.action])()
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from None
    print(json.dumps(asdict(result), ensure_ascii=False))


if __name__ == "__main__":
    main()
