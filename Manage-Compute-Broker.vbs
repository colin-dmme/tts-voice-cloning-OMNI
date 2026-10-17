Option Explicit
Dim brokerShell, brokerFso, brokerRoot, brokerPython, brokerCommand
Set brokerShell = CreateObject("WScript.Shell")
Set brokerFso = CreateObject("Scripting.FileSystemObject")
brokerRoot = brokerFso.GetParentFolderName(WScript.ScriptFullName)
brokerPython = brokerFso.BuildPath(brokerRoot, ".venv\Scripts\pythonw.exe")
If Not brokerFso.FileExists(brokerPython) Then
    MsgBox "Khong tim thay Python. Hay chay run_qt.bat de cai moi truong truoc.", 48, "Colin TTS"
    WScript.Quit 1
End If
brokerShell.CurrentDirectory = brokerRoot
brokerCommand = Chr(34) & brokerPython & Chr(34) & " -m omni_tts_ui_qt.broker_control"
brokerShell.Run brokerCommand, 1, False
