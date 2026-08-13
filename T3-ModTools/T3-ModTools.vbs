Option Explicit

Dim fso, shell, baseDir, scriptPath, command, exitCode
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
scriptPath = fso.BuildPath(baseDir, "t3_modtools.py")
shell.CurrentDirectory = baseDir

If Not fso.FileExists(scriptPath) Then
    MsgBox "t3_modtools.py was not found in:" & vbCrLf & baseDir, vbCritical, "T3-ModTools"
    WScript.Quit 2
End If

exitCode = shell.Run("cmd /c where pyw.exe >nul 2>nul", 0, True)
If exitCode = 0 Then
    command = "pyw.exe -3 " & Quote(scriptPath) & " --gui"
    shell.Run command, 0, False
    WScript.Quit 0
End If

exitCode = shell.Run("cmd /c where pythonw.exe >nul 2>nul", 0, True)
If exitCode = 0 Then
    command = "pythonw.exe " & Quote(scriptPath) & " --gui"
    shell.Run command, 0, False
    WScript.Quit 0
End If

exitCode = shell.Run("cmd /c where py.exe >nul 2>nul", 0, True)
If exitCode = 0 Then
    command = "py.exe -3 " & Quote(scriptPath) & " --gui"
    shell.Run command, 0, False
    WScript.Quit 0
End If

exitCode = shell.Run("cmd /c where python.exe >nul 2>nul", 0, True)
If exitCode = 0 Then
    command = "python.exe " & Quote(scriptPath) & " --gui"
    shell.Run command, 0, False
    WScript.Quit 0
End If

MsgBox "Python 3 was not found." & vbCrLf & vbCrLf & _
       "Install it from python.org and enable the Add Python to PATH option.", _
       vbExclamation, "T3-ModTools"
WScript.Quit 3

Function Quote(value)
    Quote = Chr(34) & value & Chr(34)
End Function
