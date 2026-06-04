' =============================================================================
' iCross Agent — Silent Windows Launcher
' =============================================================================
' Double-click this file to start iCross Agent without a visible console.
' The browser will automatically open once the servers are ready.
' =============================================================================

Dim shell, fso, projectDir, startScript, retryCount

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Get the script's directory (project root)
projectDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Change to project directory
shell.CurrentDirectory = projectDir

' Run start.bat in hidden window
startScript = projectDir & "\start.bat"
If fso.FileExists(startScript) Then
    ' Run minimized (not completely hidden so user can see if there's an error)
    shell.Run """" & startScript & """", 7, False

    ' Wait a bit and try to open the browser
    WScript.Sleep 8000

    ' Retry opening the browser a few times
    For retryCount = 1 To 5
        Dim testUrl
        testUrl = "http://localhost:3000"

        On Error Resume Next
        Dim http
        Set http = CreateObject("MSXML2.XMLHTTP")
        http.open "GET", testUrl, False
        http.send ""

        If http.Status = 200 Then
            shell.Run testUrl
            Exit For
        End If

        WScript.Sleep 3000
    Next

    If retryCount > 5 Then
        ' Even if frontend isn't ready, try to open the API docs
        shell.Run "http://localhost:8000/health"
    End If
Else
    MsgBox "启动脚本未找到: " & startScript, vbExclamation, "iCross Agent"
End If
