@echo off
setlocal

echo Stopping Omni TTS Local...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$procs = Get-CimInstance Win32_Process | Where-Object { ($_.CommandLine -like '*omni-tts-gradio*' -or $_.CommandLine -like '*tts-voice-cloning-OMNI*') -and ($_.Name -in @('uv.exe','python.exe','omni-tts-gradio.exe')) }; foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }"

echo Done.
pause
