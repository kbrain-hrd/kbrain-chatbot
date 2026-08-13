' Launch guard.ps1 with no console window at all.
'
' Running powershell.exe straight from Task Scheduler flashes a window every time,
' even with -WindowStyle Hidden: the console is created first and hidden a moment
' later. Every 5 minutes that flash covers whatever the user is doing.
'
' wscript.exe has no console of its own, so starting PowerShell from here with
' window style 0 means no window is ever created.
'
' NOTE: keep this file ASCII-only. wscript reads it with the system codepage and
' Korean text here would break on a machine with a different one - same trap the
' run.bat header describes.

Option Explicit

Dim shell, here, script

Set shell = CreateObject("WScript.Shell")
here = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
script = here & "guard.ps1"

' 0 = hidden window, False = do not wait for it to finish
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & script & """", 0, False
