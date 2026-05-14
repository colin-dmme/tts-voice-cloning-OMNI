Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)

Dim env
Set env = WshShell.Environment("Process")
env("HF_HOME") = WshShell.CurrentDirectory & "\.hf_cache"
env("HF_HUB_CACHE") = WshShell.CurrentDirectory & "\.hf_cache\hub"
env("HF_HUB_DISABLE_SYMLINKS_WARNING") = "1"

WshShell.Run """" & WshShell.CurrentDirectory & "\.venv\Scripts\pythonw.exe"" -m omni_tts_ui_tkinter.main", 0, False
