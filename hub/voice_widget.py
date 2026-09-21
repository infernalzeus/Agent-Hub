"""The conversation popover (markup + styles + script), shared by the hub menu and the Missions page.

`widget(with_orbs)` returns one HTML fragment to place before </body>. The orbs script is added only when the page does not already carry it.
"""
from __future__ import annotations

from pathlib import Path

_S = Path(__file__).parent / "static"

_HTML = """<div id="voice" hidden>
  <div class="v-head"><span>TALK TO THE HUB</span><div><button type="button" class="vbtn" id="v-size">MINIMISE</button> <button type="button" class="vbtn" id="v-close" aria-label="Close">CLOSE</button></div></div>
  <div class="v-tools">
    <select id="v-voice" aria-label="TTS voice"></select>
    <button type="button" class="vbtn" id="v-mute">SOUND ON</button>
  </div>
  <div class="v-log" id="v-log"></div>
  <div class="v-history"><button type="button" class="vbtn" id="v-history" hidden>HISTORY</button><button type="button" class="vbtn" id="v-new">NEW CHAT</button><button type="button" class="vbtn" id="v-cancel">STOP REPLY</button></div>
  <div class="v-status"><canvas data-orb="breathing" data-size="20"></canvas><span id="v-state">Ready</span></div>
  <div class="v-row"><button type="button" class="vbtn go" id="v-mic">START LISTENING</button><button type="button" class="vbtn" id="v-yes" hidden>YES</button><button type="button" class="vbtn stop" id="v-no" hidden>NO</button></div>
  <div class="v-type"><input type="text" id="v-in" placeholder="Type, or dictate with your keyboard" autocomplete="off"><button type="button" class="vbtn" id="v-go">SEND</button></div>
  <div class="v-hint" id="v-hint" hidden></div>
</div>"""


def _read(name: str) -> str:
    return (_S / name).read_text(encoding="utf-8")


def widget(with_orbs: bool = True) -> str:
    orbs = f"<script>{_read('thinking-orbs.min.js')}</script>\n" if with_orbs else ""
    return f"<style>{_read('voice.css')}</style>\n{_HTML}\n{orbs}<script>{_read('voice.js')}</script>"


TALK_BUTTON = '<button type="button" class="talk-btn" data-talk title="Talk to the hub" aria-label="Talk to the hub"><img src="/smith-icon.png" alt=""></button>'

