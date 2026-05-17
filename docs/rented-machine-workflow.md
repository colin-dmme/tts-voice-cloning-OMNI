# Rented Machine Workflow

Mục tiêu: máy chính giữ source, profile giọng và setting dùng chung; máy thuê chỉ clone/pull repo, restore state đã track trong Git rồi chạy app.

## State được đưa lên Git

`user_state/` là thư mục portable được track:

- `user_state/voices/profiles/*.json`
- `user_state/voices/samples/*`
- `user_state/settings.json`

Profile trong `user_state/` dùng đường dẫn portable như `voices/samples/name.wav`. Khi restore, app đổi đường dẫn này về đúng thư mục trên máy hiện tại.

## State không đưa lên Git

- `models/`
- `.hf_cache/`
- `outputs/`
- `logs/`
- `.venv/`
- `engines/*/.venv/`
- license, private key, token, secret

Những phần này hoặc quá lớn, hoặc phụ thuộc máy, hoặc nhạy cảm.

## Trên máy chính

Sau khi tạo/sửa profile giọng hoặc đổi setting muốn dùng chung:

```bat
Sync-State-To-Git.bat
```

Script sẽ export state hiện tại vào `user_state/`, commit riêng phần đó và push lên branch hiện tại. Nếu chỉ muốn commit local mà chưa push:

```bat
Sync-State-To-Git.bat -NoPush
```

## Trên máy thuê

Nếu máy chưa có source, chạy bootstrap từ GitHub:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/colin-dmme/tts-voice-cloning-OMNI/main/scripts/install_from_github.ps1 | iex"
```

Sau khi có source:

```bat
Start-ColinTTS.bat
```

Script sẽ:

1. Cài `uv` nếu máy chưa có.
2. Pull source mới nhất nếu repo có Git.
3. Chuẩn bị môi trường Python bằng `uv sync --inexact`.
4. Restore `user_state/` vào `voices/` và `config/ui_tkinter.json` nếu máy chưa có.
5. Mở giao diện Tkinter.

Muốn mở Gradio web UI:

```bat
Start-ColinTTS.bat -Web
```

Muốn ép restore đè state local:

```bat
Start-ColinTTS.bat -ForceState
```
