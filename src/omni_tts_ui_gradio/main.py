from __future__ import annotations

import socket

from omni_tts_core.config import AppSettings
from omni_tts_ui_gradio.components import build_app


def main() -> None:
    settings = AppSettings()
    app = build_app()
    port = _find_free_port(settings.host, settings.port)
    if port != settings.port:
        print(f"Port {settings.port} is busy. Using {port} instead.")
    app.launch(server_name=settings.host, server_port=port)


def _find_free_port(host: str, preferred_port: int, limit: int = 40) -> int:
    for port in range(preferred_port, preferred_port + limit):
        if _is_port_free(host, port):
            return port
    return preferred_port


def _is_port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) != 0


if __name__ == "__main__":
    main()
