' launch_silent.vbs
' Launches Desktop AI Assistant without showing any console window.
' Place this file in Windows Startup folder or run it directly.

Dim objShell
Set objShell = CreateObject("WScript.Shell")

' Change this path if your project is in a different location
Dim projectDir
projectDir = "C:\Users\ASHWINI\Downloads\desktop_ai"

objShell.Run "python """ & projectDir & "\main.py""", 0, False

Set objShell = Nothing
