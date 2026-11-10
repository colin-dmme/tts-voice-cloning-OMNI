"""Colab administration tools registered by the existing Studio MCP server."""
from pathlib import Path
from typing import Literal

from .client import ColabClient
from .google_mcp import GoogleColabProvider
from .settings import ColabSettings, SettingsStore, data_root


def register_tools(mcp):
    auth_sessions = {}

    @mcp.tool()
    def colab_status() -> dict:
        """Xem Colab tự động, runtime do Studio cấp và job chung với giao diện Qt."""
        client = ColabClient()
        settings = SettingsStore().load()
        return client.status() | {"auth": GoogleColabProvider(data_root(), settings.account_id).auth_status()}

    @mcp.tool()
    def colab_configure(settings: dict | None = None, oauth_client_file: str | None = None) -> dict:
        """Lưu tùy chọn Colab. Import JSON OAuth Desktop do người dùng chọn trước khi kết nối lần đầu."""
        store = SettingsStore()
        current = store.load()
        if settings is not None:
            unknown = set(settings) - set(ColabSettings.model_fields)
            if unknown:
                raise ValueError("Tùy chọn Colab không hợp lệ.")
            current = ColabSettings.model_validate(current.model_dump() | settings)
            ColabClient().configure(current)
        provider = GoogleColabProvider(data_root(), current.account_id)
        if oauth_client_file:
            provider.configure_client(Path(oauth_client_file))
        return {"settings": current.model_dump(), "auth": provider.auth_status()}

    @mcp.tool()
    def colab_auth_start() -> dict:
        """Tạo liên kết cấp quyền Google và chờ callback. Người dùng mở liên kết để xác nhận tài khoản."""
        settings = SettingsStore().load()
        previous = auth_sessions.pop(settings.account_id, None)
        if previous:
            previous.close()
        session = GoogleColabProvider(data_root(), settings.account_id).begin_auth()
        auth_sessions[settings.account_id] = session
        return {"account_id": settings.account_id, "url": session.url, "status": session.status()}

    @mcp.tool()
    def colab_auth_status() -> dict:
        """Đọc kết quả cấp quyền Colab, gồm trạng thái tài khoản và callback đang chờ."""
        settings = SettingsStore().load()
        session = auth_sessions.get(settings.account_id)
        return {"auth": GoogleColabProvider(data_root(), settings.account_id).auth_status(),
                "pending": session.status() if session else None}

    @mcp.tool()
    def colab_control(action: Literal["pause", "resume", "cancel", "release"], job_id: str | None = None) -> dict:
        """Tạm dừng/tiếp tục/hủy job hoặc yêu cầu trả runtime Colab do Studio cấp."""
        client = ColabClient()
        if action == "release":
            return client.release()
        if not job_id:
            raise ValueError("Cần job_id để điều khiển job Colab.")
        return client.control(job_id, action)
