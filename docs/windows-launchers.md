# Windows launchers and installers

## Daily entry point

Use `Start-ColinTTS.bat` after cloning the private repo onto another Windows machine. It delegates to `scripts/start_colin_tts.ps1`, prepares `uv`, syncs the main Python environment, restores `user_state/`, creates the Desktop shortcut, and opens the app.

Use `Start-ColinTTS.bat -Web` for the Gradio web UI.

## App-managed setup

The app is the preferred place to install model dependencies:

- `Tải model`: downloads the selected model payload or Hugging Face cache.
- `Cài worker/môi trường`: installs the selected provider's worker or main TTS runtime.
- `Cài GPU/CUDA`: installs the selected provider's CUDA acceleration.

The GUI calls `TtsService`, which calls `SetupService` and `worker_installation.py`. The GUI should not choose `.bat` files directly.

## Root `.bat` groups

| Group | Files | Notes |
| --- | --- | --- |
| Main launcher | `Start-ColinTTS.bat` | Use this after clone and for normal daily startup. |
| Personal state | `Sync-State-To-Git.bat` | Pushes private profile/settings state to the current Git branch. |
| Dev/debug launchers | `run_app.bat`, `run_tkinter.bat`, `stop_app.bat` | Kept for manual debugging; not the recommended first-run path. |
| Legacy auto-clone | `colin-tts-launcher.bat` | Older all-in-one launcher. Prefer `Start-ColinTTS.bat` inside a cloned repo. |
| Main runtime installers | `install_tts_deps*.bat`, `Fix-RTX50-CUDA.bat` | Used by setup actions or for manual CUDA debugging. |
| Worker installers | `install_*_worker*.bat` | Used by setup actions for VieNeu, Qwen, Valtec, F5-TTS, and Chatterbox. |

Keep root wrappers stable for compatibility, but add new setup behavior in core services rather than in GUI code.
