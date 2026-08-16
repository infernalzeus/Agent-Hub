' ============================================================================
'  Agent Hub - silent launcher + restart supervisor (with logging)
' ----------------------------------------------------------------------------
'  Double-click this (or a shortcut to it) to start Agent Hub:
'    * the server runs HIDDEN (no console window)
'    * a dedicated helper waits for the server, then opens the hub UI in its
'      own window (installed PWA if present, else a chromeless Edge --app window)
'    * this script stays alive as a tiny supervisor: the header Restart button
'      makes the hub exit code 42 and this loop relaunches it; the header X
'      (shutdown) exits 0, so the loop ends and the hub stays down.
'
'  Modes (first argument):
'    (none)      normal: start server + open a window
'    server      start the server only, no window (dormant START / agenthub://)
'    agenthub:.. same as "server" (custom-protocol invocation)
'    window <f>  internal: wait for the server, then open the window; log to <f>
'
'  Logs: every launch writes ONE file under .\logs (last 5 kept). If a window
'  won't open, read the newest logs\hub_*.log - it records every decision.
' ============================================================================

Option Explicit

Dim HUB_DIR, PYTHON, EDGE, EDGE_PROXY, PORT, APP_URL, PWA_APPID
HUB_DIR = "N:\Code\git repositories\Agent Hub"
PYTHON  = "Z:\Programs\Anaconda\python.exe"
EDGE    = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
EDGE_PROXY = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge_proxy.exe"
PORT    = 8081

Dim sh, fso
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
sh.CurrentDirectory = HUB_DIR

' The installed-PWA id and your Tailscale Serve URL are specific to YOUR
' machine/tailnet (the Serve URL is a real, identifying hostname for your
' device) -- kept OUT of this tracked script. Copy "Agent Hub.local.vbs.example"
' to "Agent Hub.local.vbs" (gitignored) and fill both in there. Running
' without it just opens plain http://localhost — works fine, you only lose
' the own-taskbar-icon + same-origin-as-phone bonuses (see README).
PWA_APPID = ""
APP_URL   = ""
Dim localCfg
localCfg = HUB_DIR & "\Agent Hub.local.vbs"
If fso.FileExists(localCfg) Then ExecuteGlobal fso.OpenTextFile(localCfg, 1).ReadAll()
If APP_URL = "" Then APP_URL = "http://localhost:" & PORT

' --- Parse mode -------------------------------------------------------------
Dim mode, isWindowOpener, serverOnly
mode = ""
If WScript.Arguments.Count > 0 Then mode = LCase(WScript.Arguments(0))
isWindowOpener = (mode = "window")
serverOnly     = (mode = "server") Or (Left(mode, 9) = "agenthub:")

' --- Logging ----------------------------------------------------------------
'  LOG_FILE   = the decision log (main + window-opener both append here). It is
'               kept UNLOCKED so the opener can always write.
'  SERVER_OUT = the server's stdout/stderr (redirected). Separate file, because
'               the redirect holds it locked while the server runs.
Dim LOG_DIR, LOG_FILE, SERVER_OUT, STAMP
LOG_DIR = HUB_DIR & "\logs"
If Not fso.FolderExists(LOG_DIR) Then fso.CreateFolder(LOG_DIR)

If isWindowOpener And WScript.Arguments.Count > 1 Then
    LOG_FILE   = WScript.Arguments(1)        ' share the parent's decision log
    SERVER_OUT = ""                          ' window-opener never runs the server
Else
    STAMP      = TimeStampNow()
    LOG_FILE   = LOG_DIR & "\hub_" & STAMP & ".log"
    SERVER_OUT = LOG_DIR & "\hub_" & STAMP & ".server.txt"
End If

Log "==== " & UCase(IIf(mode = "", "main", mode)) & " instance; pid-args=[" & JoinArgs() & "] ===="
Log "HUB_DIR=" & HUB_DIR
Log "APP_URL=" & APP_URL
Log "serverOnly=" & serverOnly & "  isWindowOpener=" & isWindowOpener

' ============================================================================
'  WINDOW-OPENER MODE: wait for the server, then open the window (logged)
' ============================================================================
If isWindowOpener Then
    Dim i, up
    up = False
    For i = 1 To 40                          ' up to ~20s
        If AlreadyRunning() Then
            up = True
            Exit For
        End If
        WScript.Sleep 500
    Next
    Log "window-opener: server listening=" & up & " after " & i & " checks"
    Dim tgtDesc
    tgtDesc = OpenAppWindow()
    Log "window-opener: launched -> " & tgtDesc
    PruneLogs
    WScript.Quit
End If

' ============================================================================
'  MAIN / SERVER MODE
' ============================================================================
If AlreadyRunning() Then
    Log "hub already listening on :" & PORT
    If Not serverOnly Then
        Log "spawning window-opener (already-running path)"
        SpawnWindowOpener
    End If
    PruneLogs
    WScript.Quit
End If

If Not serverOnly Then
    Log "spawning window-opener"
    SpawnWindowOpener
End If

Log "entering supervisor loop"
Dim code
Do
    Log "starting server: " & PYTHON & " app.py (output -> " & SERVER_OUT & ")"
    ' Run hidden; redirect the server's stdout+stderr into its own file so we can
    ' see WHY it stopped. cmd /c returns the server's exit code (42=relaunch).
    code = sh.Run("cmd /c " & PYTHON & " app.py >> """ & SERVER_OUT & """ 2>&1", 0, True)
    Log "server exited, code=" & code
Loop While code = 42
Log "supervisor loop ended (code<>42); launcher exiting"
PruneLogs
WScript.Quit

' ============================================================================
'  Helpers
' ============================================================================

' Re-invoke this script (detached) as the window-opener, sharing this log file.
Sub SpawnWindowOpener()
    sh.Run "wscript.exe """ & WScript.ScriptFullName & """ window """ & LOG_FILE & """", 0, False
End Sub

' Open the hub UI window. Returns a short description (for the log).
'  - if the hub is INSTALLED as a PWA, launch it by --app-id (own icon)
'  - else plain Edge --app (borrows Edge's icon)
' Both launch DIRECTLY (sh.Run, style 1) - the reliable path; the old
' "cmd /c timeout & start" chain silently failed in a hidden console.
Function OpenAppWindow()
    If PwaInstalled() Then
        sh.Run """" & EDGE_PROXY & """ --profile-directory=Default --app-id=" & PWA_APPID, 1, False
        OpenAppWindow = "installed PWA (app-id " & PWA_APPID & ")"
    Else
        sh.Run """" & EDGE & """ --app=" & APP_URL, 1, False
        OpenAppWindow = "Edge --app=" & APP_URL & "  (not installed as PWA -> Edge icon)"
    End If
End Function

' Is the hub installed as an Edge PWA? Edge keeps a per-app folder here once
' installed; presence of it is the reliable "installed" signal (independent of
' where/how the desktop/Start-menu shortcut is named).
Function PwaInstalled()
    Dim d
    d = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & _
        "\Microsoft\Edge\User Data\Default\Web Applications\_crx__" & PWA_APPID
    PwaInstalled = fso.FolderExists(d)
End Function

' Is the hub already listening on PORT?
'  Uses sh.Run HIDDEN (style 0) + the exit code, NOT sh.Exec: .Exec always pops a
'  visible console window on every call (that was the terminal that "flashed" on
'  launch — the main check plus the window-opener's polling). findstr exits 0 when
'  it finds a LISTENING line, so exit code 0 = the hub is up.
Function AlreadyRunning()
    Dim code
    code = sh.Run("cmd /c netstat -ano -p tcp | findstr "":" & PORT & " "" | findstr LISTENING", 0, True)
    AlreadyRunning = (code = 0)
End Function

Sub Log(msg)
    On Error Resume Next
    Dim f
    Set f = fso.OpenTextFile(LOG_FILE, 8, True)   ' 8=ForAppending, create if missing
    f.WriteLine Now() & "  " & msg
    f.Close
    On Error GoTo 0
End Sub

' Keep only the newest 5 hub_*.log files.
Sub PruneLogs()
    On Error Resume Next
    Dim fld, fl, coll
    Set fld = fso.GetFolder(LOG_DIR)
    Set coll = CreateObject("System.Collections.ArrayList")
    For Each fl In fld.Files
        If LCase(Left(fl.Name, 4)) = "hub_" And LCase(fso.GetExtensionName(fl.Name)) = "log" Then
            coll.Add fl.Name
        End If
    Next
    coll.Sort                                   ' names start hub_<timestamp> -> chronological
    Dim base, stamp
    Do While coll.Count > 5
        base = coll(0)                          ' hub_<stamp>.log
        fso.DeleteFile LOG_DIR & "\" & base, True
        ' Delete the matching server-output file for this launch, if any.
        stamp = Mid(base, 5, Len(base) - 8)     ' strip leading "hub_" and trailing ".log"
        If fso.FileExists(LOG_DIR & "\hub_" & stamp & ".server.txt") Then _
            fso.DeleteFile LOG_DIR & "\hub_" & stamp & ".server.txt", True
        coll.RemoveAt 0
    Loop
    On Error GoTo 0
End Sub

Function TimeStampNow()
    Dim d : d = Now()
    TimeStampNow = Year(d) & Pad(Month(d)) & Pad(Day(d)) & "_" & Pad(Hour(d)) & Pad(Minute(d)) & Pad(Second(d))
End Function

Function Pad(n)
    If n < 10 Then Pad = "0" & n Else Pad = CStr(n)
End Function

Function IIf(cond, a, b)
    If cond Then IIf = a Else IIf = b
End Function

Function JoinArgs()
    Dim s, k
    s = ""
    For k = 0 To WScript.Arguments.Count - 1
        If k > 0 Then s = s & " "
        s = s & WScript.Arguments(k)
    Next
    JoinArgs = s
End Function
