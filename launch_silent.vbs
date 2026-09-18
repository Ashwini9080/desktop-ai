' launch_silent.vbs
' Launches Desktop AI Assistant without showing any console window.
' Works from any folder or when shortcut placed in Windows Startup.

Option Explicit

Dim fso, objShell, projectDir, pythonExe

Set fso = CreateObject("Scripting.FileSystemObject")
Set objShell = CreateObject("WScript.Shell")

' Dynamically detect project root folder
projectDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Prefer pythonw in venv if present, otherwise system pythonw
If fso.FileExists(projectDir & "\venv\Scripts\pythonw.exe") Then
    pythonExe = """" & projectDir & "\venv\Scripts\pythonw.exe"""
ElseIf fso.FileExists(projectDir & "\.venv\Scripts\pythonw.exe") Then
    pythonExe = """" & projectDir & "\.venv\Scripts\pythonw.exe"""
Else
    pythonExe = "pythonw"
End If

objShell.CurrentDirectory = projectDir
objShell.Run pythonExe & " """ & projectDir & "\main.py""", 0, False

Set objShell = Nothing
Set fso = Nothing
