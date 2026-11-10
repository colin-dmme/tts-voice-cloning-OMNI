Option Explicit
Dim colabShell, colabFso, colabRoot, colabPython, colabCommand
Set colabShell = CreateObject("WScript.Shell")
Set colabFso = CreateObject("Scripting.FileSystemObject")
colabRoot = colabFso.GetParentFolderName(WScript.ScriptFullName)
colabPython = colabFso.BuildPath(colabRoot, ".venv\Scripts\pythonw.exe")
If Not colabFso.FileExists(colabPython) Then
    MsgBox "Hay chay run_qt.bat de cai moi truong truoc.", 48, "Colin TTS"
    WScript.Quit 1
End If
colabShell.CurrentDirectory = colabRoot
colabCommand = Chr(34) & colabPython & Chr(34) & " -m colin_colab_remote panel"
colabShell.Run colabCommand, 1, False
