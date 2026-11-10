Option Explicit
Dim studioShell, studioFiles, studioRoot, studioPython
Set studioShell = CreateObject("WScript.Shell")
Set studioFiles = CreateObject("Scripting.FileSystemObject")
studioRoot = studioFiles.GetParentFolderName(WScript.ScriptFullName)
studioPython = studioFiles.BuildPath(studioRoot, ".venv\Scripts\pythonw.exe")
If Not studioFiles.FileExists(studioPython) Then
    MsgBox "Hay chay run_qt.bat de cai moi truong truoc.", 48, "Colin TTS"
    WScript.Quit 1
End If
studioShell.CurrentDirectory = studioRoot
studioShell.Run Chr(34) & studioPython & Chr(34) & " -m colin_remote_compute", 1, False
