---
name: desktop-control-windows
description: "Driving a Windows PC programmatically without a vision model — UI Automation accessibility tree, PowerShell SendKeys, clipboard, direct URL construction. Relevant when the task involves: desktop automation, computer use, GUI automation, windows-use, uiautomation, pywinauto, sendkeys, no-vision agent, controlling an app."
metadata:
  keywords: "desktop-control, computer-use, gui-automation, windows-use, uiautomation, pywinauto, sendkeys, automation, autohotkey, flaui"
  origin: hand-written
---

# Windows desktop control (no vision model)

Deterministic PC control that does not depend on a multimodal model reading
screenshots. Screenshot + "find and click the button" fails silently when the
element isn't matched and breaks on any resolution/theme/DPI change — avoid it
where a structural interface exists.

## Reach for these, in order

- **UI Automation accessibility tree** (`uiautomation` or `pywinauto` in Python,
  FlaUI in .NET) — reads real structure from any Win32 / WPF / UWP window:
  control types, names, values, states, hierarchy. Target elements by
  `AutomationId` or `Name`, never by pixel. Can **read** (button labels, field
  contents) as well as act, which SendKeys cannot.
  ```python
  import uiautomation as auto
  w = auto.WindowControl(searchDepth=1, Name="Calculator")
  w.SetActive()
  w.ButtonControl(Name="Seven").Click()
  print(w.TextControl(AutomationId="CalculatorResults").Name)
  ```
- **PowerShell SendKeys** — inject keystrokes into the focused window. No deps,
  works on almost anything, but write-only and needs focus first. Escape
  `{ } + ^ % ~ ( )`. Use for a quick "type this and press Enter" where UIA setup
  isn't worth it.
- **Clipboard paste** — put text on the clipboard, send `^v`, then `~`. More
  reliable than SendKeys for long / unicode / special-character text.
- **Direct URL / protocol construction** — for anything web, skip the UI: build
  the target URL (`https://youtube.com/results?search_query=<enc>`) and open it.
  Same for registered protocol handlers (`mailto:`, custom `app://` schemes).
- **Keyboard shortcuts** — app-specific `Tab` / `/` / `Ctrl+…` sequences. Fast
  but brittle across versions; document the exact sequence.
- **Coordinates** — last resort only. If unavoidable, anchor to a found
  element's bounding rect, never absolute screen pixels.

## The reliable launch-and-act pattern

1. Launch the app **once** (`start`, `Start-Process`, or the exe path). Calling
   launch again spawns duplicate instances.
2. **Wait** for the window to exist (poll for the window/title), don't fixed-sleep.
3. Bring it to the foreground (`SetActive()` / `AppActivate`) before any SendKeys.
4. Act via UIA; fall back to SendKeys/clipboard only if no automation element.

## Guardrails

- **Tier the capability**: read-only (screenshot, read tree, read files) is safe
  by default; input (type, click, shortcuts) is a step up; running shell/Python
  is an explicit grant; destructive actions (delete, format, install, send,
  spend) always confirm with the user first.
- **Never drive a login / payment / credential field** — hand that to the user.
- **Prefer an API or a file write over UI poking** whenever the app has one; UI
  automation is the fallback for apps that give you nothing else.
- **A silent no-op is the failure mode.** After an action, verify via UIA
  (field now holds the value, window state changed) rather than assuming it took.

## See also

- **`windows-automation`** — PowerShell / Task Scheduler / services / registry,
  for automating the machine rather than driving a GUI.
- **`browser-control`** — when the "app" is a web page.
- The LLM-wiki page `windows-computer-control` has the longer background and the
  reliability ranking table this skill is distilled from.
