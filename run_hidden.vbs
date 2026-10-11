' Run MediaFlow quietly in the background without displaying a command window
Set WshShell = CreateObject("WScript.Shell")
strPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strPath
WshShell.Run """" & strPath & "\start.bat""", 0, False
