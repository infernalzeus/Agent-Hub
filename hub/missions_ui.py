"""The mission board — dispatch and review distributed autonomous agent runs.

A real page (not an overlay): one top bar, its own `← HUB`. Reads
hub/features/missions.py:
  GET  /api/projects
  GET  /api/missions                 board
  POST /api/missions                 {project, brief, kind, agent?, model?}
  GET  /api/missions/{id}            detail + events + children
  GET  /api/missions/{id}/events     SSE
  GET  /api/missions/{id}/diff[?path]
  POST /api/missions/{id}/{abort,apply,discard,retry,continue,dispatch,transcript}
  POST /api/missions/plan/{id}/dispatch-all
  GET  /api/agents                   personas for the New-Mission agent picker
"""
from __future__ import annotations

from aiohttp import web

routes = web.RouteTableDef()

from pathlib import Path as _P

from .voice_widget import TALK_BUTTON, widget as _widget

_ORBS_JS = (_P(__file__).parent / "static" / "thinking-orbs.min.js").read_text(encoding="utf-8")
_WIDGET = _widget(False)      # the orbs script is already in this page   # thinking-orbs (MIT), see static/THINKING-ORBS-LICENSE.txt

_HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="color-scheme" content="dark"><meta name="theme-color" content="#080c28">
<title>AGENT HUB — Missions</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600&family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#080c28;--bg-mid:#0d1050;--panel:rgba(8,12,40,0.88);
  --border-dim:rgba(0,230,118,0.22);--border-bright:rgba(0,230,118,0.55);
  --accent:#00e676;--text:rgba(0,230,118,0.90);--text-muted:rgba(0,230,118,0.52);--text-faint:rgba(0,230,118,0.22);
  --red:#ff5c5c;--amber:#e0a53c;--blue:#3ba7ff;--purple:#b07cd6;
}
html{min-height:100dvh;background:linear-gradient(150deg,#080c28 0%,#0d1050 45%,#18095c 100%) fixed}
html,body{height:100%;font-family:'Outfit',system-ui,sans-serif;color:var(--text)}
body{display:flex;flex-direction:column;overflow:hidden}
a{color:var(--accent);text-decoration:none}
button,input,select,textarea{font-family:'Outfit',inherit}
.bar{display:flex;align-items:center;gap:10px;padding:calc(9px + env(safe-area-inset-top)) 14px 9px;border-bottom:1px solid var(--border-dim);flex:0 0 auto;flex-wrap:wrap}
.brand{font-family:'Orbitron',monospace;font-weight:900;letter-spacing:3px;font-size:13px;color:var(--accent);text-shadow:0 0 16px rgba(0,230,118,.35)}
.spacer{flex:1}
.btn{font-family:'Orbitron',monospace;font-size:9px;letter-spacing:1px;padding:9px 12px;min-height:36px;border-radius:6px;
  display:inline-flex;align-items:center;justify-content:center;
  border:1px solid var(--border-bright);background:transparent;color:var(--accent);cursor:pointer;white-space:nowrap;transition:all .15s;-webkit-tap-highlight-color:transparent}
.btn:hover:not(:disabled){background:rgba(0,230,118,.1);box-shadow:0 0 10px rgba(0,230,118,.18)}
.btn:disabled{opacity:.35;cursor:not-allowed}
.btn.stop{border-color:rgba(255,92,92,.5);color:var(--red)}
.btn.stop:hover:not(:disabled){background:rgba(255,92,92,.1)}
.btn.go{border-color:var(--accent);background:rgba(0,230,118,.12)}
.body{flex:1;display:flex;min-height:0}
.list{width:340px;flex:0 0 auto;overflow-x:hidden;border-right:1px solid var(--border-dim);overflow-y:auto;background:var(--panel);padding:8px}
.ck{min-height:32px}
.ck input{width:auto;min-width:20px;min-height:20px}
.backbtn{display:none}
.xbtn{width:26px;height:26px;border-radius:6px;border:1px solid var(--border-dim);background:transparent;color:var(--accent);display:inline-flex;align-items:center;justify-content:center;cursor:pointer;padding:0;flex:none}
.xbtn:hover{background:rgba(0,230,118,.12);border-color:var(--border-bright)}
.xbtn svg{width:16px;height:16px;display:block}
@media (max-width:720px){
  html,body{height:auto;min-height:100dvh}
  body{overflow:auto}
  .body{flex:none;flex-direction:column;min-height:0}
  .list,.list.wide{width:100%;max-height:none;border-right:none;border-bottom:none;overflow:visible;padding:10px 12px 28px}
  .xbtn{display:none}
  .detail{overflow:visible;min-height:60vh}
  .dscroll{overflow:visible;padding:12px}
  .dhead{padding:10px 12px}
  .body.m-detail .list{display:none}
  .body:not(.m-detail) .detail{display:none}
  .backbtn{display:inline-flex;margin-bottom:8px}
  .bar{gap:8px;padding:calc(8px + env(safe-area-inset-top)) 12px 8px}
  .bar .spacer{display:none}
  .bar .brand{flex:1 1 auto;margin:0}
  .bar .btn{flex:1 1 0;min-width:0;padding:8px 6px}
  .bar #btn-new{flex:1 0 100%;order:2}
  .bar #btn-arch,.bar a[href="/agents"],.bar a[href="/graph"]{order:3}.bar #btn-reload{order:3;flex:0 0 42px;align-self:stretch;padding:8px}
  .bar #btn-arch .lbl{display:none}
  .card{padding:12px}
  .banner .row .btn,.row .btn{flex:1 1 calc(50% - 8px)}
  .modal,.modal.wide{top:2vh;max-width:96vw;max-height:94vh}
  .info .tip{position:fixed;left:12px;right:12px;top:72px}
}
.grp{font-family:'Orbitron',monospace;font-size:8px;letter-spacing:1.5px;color:var(--text-faint);margin:12px 6px 5px}
.card{border:1px solid transparent;border-radius:9px;padding:10px 11px;cursor:pointer;margin-bottom:5px}
.card:hover{border-color:var(--border-dim)}
.card.sel{border-color:var(--border-bright);background:rgba(0,230,118,.06)}
.card.child{margin-left:18px}
.card .top{display:flex;align-items:center;gap:8px}
.card .ag{font-weight:600;font-size:12.5px}
.card .br{font-size:11.5px;color:var(--text-muted);margin-top:3px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card .mt{font-size:10px;color:var(--text-faint);margin-top:4px;display:flex;gap:10px}
.dot{width:9px;height:9px;border-radius:50%;background:var(--text-faint);flex:0 0 auto}
.dot.running{background:var(--amber);box-shadow:0 0 8px var(--amber);animation:pulse 1.1s infinite}
.dot.awaiting_review{background:var(--accent);box-shadow:0 0 8px var(--accent)}
.dot.applied{background:#3aa0ff}
.dot.failed,.dot.timed_out{background:var(--red);box-shadow:0 0 8px var(--red)}
.dot.discarded{background:#555}
.dot.proposed{background:var(--purple);box-shadow:0 0 8px var(--purple)}
.dot.blocked{background:var(--text-faint);border:2px solid var(--amber)}
.dot.orphaned{background:#555;border:2px solid var(--purple)}
@keyframes pulse{50%{opacity:.35}}
.detail{flex:1;display:flex;flex-direction:column;min-width:0;overflow:hidden}
.dhead{padding:12px 16px;border-bottom:1px solid var(--border-dim);flex:0 0 auto}
.dhead h1{font-size:15px;font-weight:600}
.dhead .sub{font-size:11px;color:var(--text-muted);margin-top:3px;display:flex;gap:12px;flex-wrap:wrap;align-items:center}
.dscroll{flex:1;overflow-y:auto;padding:16px}
h2{font-family:'Orbitron',monospace;font-size:9px;letter-spacing:1.5px;color:var(--text-faint);margin:18px 0 8px}
h2:first-child{margin-top:0}
.files li{font-size:12px;font-family:ui-monospace,Consolas,monospace;padding:5px 8px;border-radius:5px;cursor:pointer;list-style:none}
.files li:hover{background:rgba(0,230,118,.06)}
.badge{display:inline-block;width:16px;text-align:center;color:var(--amber);margin-right:6px}
pre{background:var(--bg);border:1px solid var(--border-dim);border-radius:8px;padding:12px;overflow:auto;
  font-size:11.5px;line-height:1.45;white-space:pre;max-height:44vh}
.diff-add{color:#5dd88a}.diff-del{color:#ff8080}
.feed{background:var(--bg);border:1px solid var(--border-dim);border-radius:8px;padding:10px;font-family:ui-monospace,Consolas,monospace;
  font-size:11px;line-height:1.5;max-height:40vh;overflow-y:auto}
.feed .tool{color:var(--blue)}.feed .text{color:var(--text)}.feed .err{color:var(--red)}.feed .step,.feed .reasoning{color:var(--text-faint)}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
label{display:block;font-family:'Orbitron',monospace;font-size:8px;letter-spacing:1px;color:var(--text-faint);margin:14px 0 5px}
input[type=text],select,textarea{width:100%;background:var(--bg);border:1px solid var(--border-dim);color:var(--text);
  border-radius:6px;padding:9px 10px;font-size:13px;outline:none}
input:focus,select:focus,textarea:focus{border-color:var(--accent)}
input[type=time],input[type=number]{background:var(--bg);border:1px solid var(--border-dim);color:var(--text);border-radius:6px;padding:9px 10px;font-size:13px;outline:none;color-scheme:dark}
textarea{min-height:120px;resize:vertical}
.hollow{flex:1;display:flex;align-items:center;justify-content:center;color:var(--text-faint);font-size:13px}
.note{font-size:11px;color:var(--amber);margin-top:6px}
.pill{font-family:'Orbitron',monospace;font-size:8px;letter-spacing:.5px;padding:2px 7px;border-radius:999px;border:1px solid var(--border-dim);color:var(--text-muted)}
.cklist{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:4px;background:var(--bg);border:1px solid var(--border-dim);border-radius:6px;padding:9px 10px}
.ck{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text);margin:0}
.ck input{width:auto}
.chip{display:inline-flex;align-items:center;gap:6px;background:var(--bg);border:1px solid var(--border-dim);border-radius:6px;padding:4px 8px;margin:3px 4px 0 0;font-size:12px}
.chip button{background:transparent;border:1px solid var(--border-dim);color:var(--text-muted);border-radius:4px;cursor:pointer;font-size:11px;padding:0 5px;line-height:1.6}
.chip button:disabled{opacity:.3;cursor:default}
.btn.sel{border-color:var(--accent);background:rgba(0,230,118,.14);color:var(--accent)}
#toast{position:fixed;left:50%;bottom:20px;transform:translateX(-50%) translateY(10px);z-index:99;max-width:min(460px,92vw);
  padding:11px 15px;border-radius:9px;font-size:12px;background:var(--panel);border:1px solid var(--border-bright);
  color:var(--text);box-shadow:0 8px 28px rgba(0,0,0,.5);opacity:0;pointer-events:none;transition:opacity .2s,transform .2s}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
#toast.err{border-color:rgba(255,92,92,.6);color:#ffb3b3}
.scrim{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;z-index:30}
.scrim.open{display:block}
.modal{position:fixed;top:6vh;left:50%;transform:translateX(-50%);width:600px;max-width:94vw;max-height:86vh;overflow-y:auto;
  background:var(--bg-mid);border:1px solid var(--border-bright);border-radius:12px;padding:18px 20px;z-index:31;display:none}
.modal.open{display:block}
.modal h2{font-family:'Orbitron',monospace;font-size:12px;letter-spacing:1.5px;color:var(--accent);margin-bottom:14px}
.flow{font-family:ui-monospace,Consolas,monospace;font-size:12.5px;line-height:1.5}
.flow .st{color:var(--accent);font-weight:700}
.flow .arrow{color:var(--text-faint);text-align:center;margin:1px 0}
.flow .d{color:var(--text-muted);margin:0 0 8px 0}
.flow .you{color:var(--amber);font-weight:700}
.runmap{display:flex;flex-direction:column;gap:8px}
.rm-row{display:grid;grid-template-columns:150px 1fr;gap:4px 12px;align-items:center;background:var(--bg);border:1px solid var(--border-dim);border-radius:8px;padding:8px 10px}
.rm-who{display:flex;flex-direction:column;line-height:1.25;min-width:0}
.rm-who b{font-size:12.5px}.rm-who span{font-size:10px;color:var(--text-faint);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rm-bar{position:relative;height:16px;background:rgba(0,230,118,.06);border-radius:4px;overflow:hidden}
.rm-bar i{position:absolute;left:0;top:0;bottom:0;border-radius:4px;background:var(--amber);opacity:.75}
.rm-bar i.ok{background:var(--accent)}.rm-bar i.bad{background:var(--red)}
.rm-bar em{position:absolute;left:8px;top:0;line-height:16px;font-style:normal;font-size:10.5px;color:#fff;text-shadow:0 0 3px #000}
.rm-meta{grid-column:1/-1;font-size:10.5px;color:var(--text-muted);font-family:ui-monospace,Consolas,monospace;word-break:break-word}
.chk{border:1px solid var(--border-dim);border-radius:8px;padding:9px 12px;font-size:12px}
.chk.ok{border-color:rgba(0,230,118,.5)}.chk.bad{border-color:rgba(255,92,92,.55);color:#ffb3b3}
.chk pre{margin-top:6px;max-height:16vh;font-size:11px}
@media (max-width:720px){.rm-row{grid-template-columns:1fr}}
.dot.needs_input{background:var(--amber);box-shadow:0 0 8px var(--amber)}
.dot.plan_ready{background:var(--purple);box-shadow:0 0 8px var(--purple)}
.dot.queued{background:var(--purple)}
.cv{border:1px solid var(--border-dim);border-radius:9px;background:rgba(8,12,40,.55);overflow-x:auto}
.pwrap{margin:10px;position:relative}
.pcanvas{position:relative}
.pcanvas svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;overflow:visible}
.pn{position:absolute;width:134px;height:90px;background:rgba(13,16,80,.75);border:1px solid var(--border-dim);border-radius:9px;padding:7px 9px;text-align:left;
  color:var(--text);cursor:pointer;overflow:hidden;font-family:inherit;transition:border-color .2s,box-shadow .2s}
.pn:hover{border-color:var(--border-bright)}
.pn.sel{border-color:var(--accent);box-shadow:0 0 12px rgba(0,230,118,.35)}
.pn.hub{border-style:dashed}
.pn.running{border-color:var(--amber);box-shadow:0 0 12px rgba(224,165,60,.3)}
.pn.wait{border-color:var(--amber);box-shadow:0 0 10px rgba(224,165,60,.3)}
.pn.proposed{border-color:rgba(176,124,214,.7)}
.pn.fail{border-color:var(--red);box-shadow:0 0 12px rgba(255,92,92,.3)}
.pn .hd{display:flex;align-items:center;gap:6px;font-family:'Orbitron',monospace;font-size:8.5px;letter-spacing:1px;font-weight:700}
.pn .hd .tm{margin-left:auto;font-family:'Outfit';font-weight:400;font-size:10px;color:var(--text-faint);letter-spacing:0}
.pn .tg{font-size:10px;color:var(--text-muted);margin:2px 0 4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pn .io{display:block;font-size:10.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--text-muted)}
.pn .io em{font-style:normal;font-family:'Orbitron',monospace;font-size:7px;letter-spacing:1px;margin-right:5px;color:var(--purple)}
.pn .io.o em{color:var(--accent)}
.pn .st{position:absolute;left:9px;right:9px;bottom:6px;font-size:10px;color:var(--amber);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pe{font-size:9.5px;fill:rgba(0,230,118,.52)}
.pleg{padding:2px 12px 9px;font-size:10.5px;color:var(--text-muted);display:flex;gap:16px;flex-wrap:wrap}
.pdraw{border:1px solid var(--border-dim);border-radius:9px;padding:11px;margin-top:10px;background:rgba(8,12,40,.6)}
.pdraw .kv{display:grid;grid-template-columns:auto 1fr;gap:2px 12px;font-size:11.5px;margin:6px 0}
.pdraw .kv span:nth-child(odd){color:var(--text-muted)}
.pdraw pre{max-height:150px;margin:4px 0 8px;font-size:11px;white-space:pre-wrap}
.pdraw .lb{font-family:'Orbitron',monospace;font-size:8px;letter-spacing:1.5px;color:var(--text-faint);margin:8px 0 3px}
.ask{border:1px solid var(--amber);border-radius:9px;padding:12px;background:rgba(224,165,60,.07);margin-bottom:12px}
.ask h3{font-family:'Orbitron',monospace;font-size:9px;letter-spacing:1.5px;color:var(--amber);margin-bottom:8px}
.ask .q{margin-bottom:10px}.ask .q b{font-weight:600;display:block}
.ask .q i{font-style:normal;font-size:11px;color:var(--text-muted);display:block;margin:1px 0 5px}
.ask .chips{display:flex;gap:6px;flex-wrap:wrap}
.pick{background:transparent;border:1px solid var(--border-dim);color:var(--text);border-radius:14px;padding:3px 11px;font-size:12px;cursor:pointer}
.pick.sel{border-color:var(--amber);color:var(--amber);background:rgba(224,165,60,.1)}
.pick.rec::after{content:" \2605";color:var(--amber)}
.ask input[type=text]{margin-top:6px;font-size:12px;padding:6px 9px}
.sect{font-family:'Orbitron',monospace;font-size:9px;letter-spacing:1.5px;margin:14px 6px 6px;display:flex;align-items:center;gap:8px;cursor:default}
.sect.needs{color:var(--accent)}.sect.run{color:var(--amber)}.sect.hist{color:var(--text-faint);cursor:pointer}
.sect .n{border:1px solid currentColor;border-radius:999px;padding:0 7px;font-size:9px}
.sect small{font-family:'Outfit',sans-serif;letter-spacing:.2px;color:var(--text-muted);font-size:10.5px}
.tag-act{font-family:'Orbitron',monospace;font-size:8px;letter-spacing:1px;font-weight:700;padding:3px 8px;border-radius:999px;white-space:nowrap}
.tag-review{background:var(--accent);color:#04160c}
.tag-answer{background:var(--amber);color:#1a1200}
.tag-dispatch{background:var(--purple);color:#14051f}
.card.needs{border-color:var(--border-dim);background:rgba(0,230,118,.04)}
.card .pj{font-size:10px;color:var(--text-faint);letter-spacing:.3px;margin-bottom:1px}
.listhelp{font-size:11px;line-height:1.45;color:var(--text-muted);border:1px dashed var(--border-dim);border-radius:8px;padding:8px 10px;margin:2px 2px 6px}
.listhelp b{color:var(--accent);font-weight:600}
.colcap{font-size:11px;color:var(--text-muted);margin:6px 0 0;line-height:1.45}
.colcap b{color:var(--accent);font-weight:600}
.pstrip{display:flex;flex-wrap:wrap;align-items:center;gap:3px 5px;font-size:10.5px;color:var(--text-muted);margin-top:4px}
.pstrip .pd{display:inline-flex;align-items:center;gap:3px}
.pstrip .pd i{width:7px;height:7px;border-radius:50%;background:var(--text-faint);display:inline-block}
.pstrip .pd.done i{background:var(--accent)}.pstrip .pd.running i{background:var(--amber);animation:pulse 1s infinite}
.pstrip .pd.failed i{background:var(--red)}.pstrip .pd.queued i,.pstrip .pd.proposed i{background:var(--purple)}
.pstrip .ar{color:var(--text-faint)}
.card .asktxt{font-weight:600;font-size:12.5px;line-height:1.35;margin-top:5px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;color:var(--text)}
.mhead{display:flex;align-items:center;gap:8px;margin:2px 4px 8px;position:relative}
.mtitle{font-family:'Orbitron',monospace;font-weight:900;font-size:13px;letter-spacing:3px;color:var(--accent)}
.msub{font-size:10.5px;color:var(--text-muted);margin-left:auto}
.info{position:static;width:24px;height:24px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;color:var(--accent);cursor:help;outline:none;transition:background .15s}
.info svg{width:22px;height:22px;display:block;shape-rendering:geometricPrecision}
.info:hover,.info:focus{background:rgba(0,230,118,.14)}
.ic{width:1.2em;height:1.2em;vertical-align:-.24em;margin-right:.38em;flex:none;shape-rendering:geometricPrecision}
.btn .ic{width:15px;height:15px;vertical-align:-3px;margin-right:7px}
.pj .ic,.pill .ic,.mt .ic{color:var(--text-muted)}.note .ic{color:var(--amber)}.mt .ic{width:1.1em;height:1.1em}
.feed .ic{width:13px;height:13px;margin-right:6px;vertical-align:-2px;color:var(--text-muted)}.feed .err .ic{color:var(--red)}
.info .tip{display:none;position:absolute;left:0;right:0;top:100%;margin-top:6px;z-index:40;background:var(--bg-mid);border:1px solid var(--border-bright);border-radius:10px;padding:10px 12px;font-size:11.5px;line-height:1.5;color:var(--text);box-shadow:0 8px 28px rgba(0,0,0,.55);font-family:'Outfit',sans-serif;letter-spacing:0;font-weight:400}
.info .tip b{color:var(--accent);font-weight:600}
.info .tip .th{font-family:'Orbitron',monospace;font-size:9.5px;letter-spacing:1.6px;color:var(--accent);font-weight:700;margin-bottom:6px}
.info .tip ol{list-style:none;margin:0;padding:0}
.info .tip li{display:grid;grid-template-columns:20px 1fr;gap:9px;align-items:start;margin:0 0 7px}
.info .tip li i{font-style:normal;width:20px;height:20px;border-radius:50%;background:rgba(0,230,118,.14);border:1px solid var(--border-bright);color:var(--accent);font:700 10px 'Orbitron',monospace;display:flex;align-items:center;justify-content:center}
.info .tip li.you i{background:var(--amber);border-color:var(--amber);color:#1a1200}
.info .tip .tf{margin-top:8px;padding-top:8px;border-top:1px solid var(--border-dim);color:var(--text-muted);font-size:11px}
.info:hover .tip,.info:focus .tip{display:block}
.tag-resume{background:var(--amber);color:#1a1200}
.card .asktxt{-webkit-line-clamp:1;margin-top:4px}
.card.open{border-color:var(--border-bright);background:rgba(0,230,118,.05)}
.card.open .asktxt{-webkit-line-clamp:6}
.card .chev{display:inline-flex;color:var(--text-muted);margin-left:4px}.card .chev svg{width:14px;height:14px}
.deep{margin-top:9px;padding-top:9px;border-top:1px solid var(--border-dim);display:grid;gap:6px;font-size:11.5px;color:var(--text)}
.deep .dstep{display:grid;grid-template-columns:8px auto 1fr auto;gap:7px;align-items:center}
.deep .dstep .dot{width:7px;height:7px}.deep .dstep .dm{color:var(--text-muted);font-size:10.5px;text-align:right}
.deep .dstep .dt{color:var(--text-faint);font-size:10.5px;grid-column:1/-1;line-height:1.35;margin:-2px 0 2px 15px}
.deep .dline{color:var(--text-muted);font-size:11px;display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center}
.deep .dline .ic{width:12px;height:12px;margin-right:4px}
.deep .dhint{color:var(--text-faint);font-size:10.5px}
@media (max-width:720px){.deep{display:none}.card .chev{display:none}}
/* ---- the ask window: a thread of messages ---- */
.orb{display:inline-block;vertical-align:middle}
.tmsg{max-width:88%;font-size:13px;line-height:1.55;color:var(--text)}
.tmsg.me{align-self:flex-end;margin-left:auto;background:rgba(0,230,118,.14);border:1px solid var(--border-bright);border-radius:14px 14px 3px 14px;padding:9px 13px;width:fit-content;margin-bottom:12px;color:#d9ffe9}
.tbot{margin-bottom:14px}
.twho{display:flex;align-items:center;gap:7px;font:700 9px 'Orbitron',monospace;letter-spacing:1.4px;color:var(--accent);margin-bottom:5px;flex-wrap:wrap}
.twho .ic{width:16px;height:16px;margin:0}.twho .tm2{font:400 10.5px 'Outfit';letter-spacing:0;color:var(--text-faint);margin-left:4px}
.tblk{border:1px solid var(--border-dim);border-radius:11px;padding:11px 12px;background:rgba(0,0,0,.22)}
.tblk .banner{margin:0 0 10px}
.tact{display:grid;grid-template-columns:150px 1fr 48px minmax(0,150px);gap:9px;align-items:center;font-size:11.5px;color:#d9ffe9;margin:6px 0}
.tact .tag2{display:flex;align-items:center;gap:6px;min-height:20px}.tact .orbgap{width:20px;flex:none}
.tbar2{height:5px;border-radius:3px;background:rgba(0,230,118,.12);overflow:hidden;display:block}
.tbar2 i{display:block;height:100%;background:var(--accent)}.tbar2 i.run{background:var(--amber);animation:pulse 1s infinite}.tbar2 i.bad,.tbar2 i.b{background:var(--red)}.tbar2 i.w{background:var(--amber)}
.tm2{font-size:10.5px;color:var(--text-muted);text-align:right}.tmod{font-size:10.5px;color:var(--text-faint);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tjrow{display:grid;grid-template-columns:minmax(0,1fr) 110px 86px 128px;gap:9px;align-items:center;font-size:11.5px;color:#d9ffe9;padding:6px 0;border-bottom:1px solid var(--border-dim)}
.tjrow:last-of-type{border:0}.tjrow .tp{font:700 10.5px 'Orbitron',monospace;color:var(--accent);text-align:right}.tjrow .tp.w{color:var(--amber)}.tjrow .tp.b{color:var(--red)}.tjrow .tp.mut{color:var(--text-faint);font-weight:400}
.tsrc{font-size:9.5px;color:var(--text-muted);text-align:right}.tsrc .btn{min-height:28px;padding:5px 8px;font-size:8px}
.tnote{font-size:11px;color:var(--text-muted);margin-top:8px;line-height:1.5}
.tfold{margin:6px 0 14px}.tfold>summary{cursor:pointer;font:700 9px 'Orbitron',monospace;letter-spacing:1.4px;color:var(--text-muted);padding:8px 2px}
.tbar{border-top:1px solid var(--border-dim);padding:10px 14px;flex:0 0 auto;background:var(--panel)}
.tin{display:flex;align-items:center;gap:9px;border:1px solid var(--border-bright);border-radius:12px;padding:6px 10px;background:rgba(0,0,0,.3)}
.tin .ic{width:20px;height:20px;margin:0;color:var(--accent)}.tin input{flex:1;background:transparent;border:0;color:#d9ffe9;font-size:13px;padding:6px 0;min-width:0}
.tin input:focus{outline:none}.tkey{font:700 9px 'Orbitron',monospace;border:1px solid var(--border-dim);border-radius:6px;padding:3px 7px;color:var(--text-muted)}
.tslash{font-size:10.5px;color:var(--text-faint);margin-top:6px}
.dial{display:grid;grid-template-columns:repeat(3,1fr);gap:5px;margin:4px 0}
.dial button{border:1px solid var(--border-dim);border-radius:8px;padding:9px 4px;background:transparent;color:var(--text-muted);font:700 8.5px 'Orbitron',monospace;letter-spacing:.8px;line-height:1.4;cursor:pointer}
.dial button.on{background:rgba(0,230,118,.16);border-color:var(--accent);color:#d9ffe9}
@media (max-width:720px){.tact{grid-template-columns:96px 1fr 40px}.tact .tmod{display:none}.tjrow{grid-template-columns:1fr 70px;grid-auto-rows:auto}.tjrow .tbar2,.tjrow .tsrc{grid-column:auto}.tjrow .tbar2{display:none}.tmsg{max-width:96%}.tbar{padding:8px 10px}.tslash{display:none}}
.dot.paused{background:var(--amber);box-shadow:0 0 6px var(--amber)}
h1.asktitle{font-size:16px;line-height:1.35;font-weight:600}
.banner{border:1px solid var(--border-dim);border-radius:10px;padding:12px 14px;margin:0 0 14px;display:grid;gap:6px}
.banner .bt{font-family:'Orbitron',monospace;font-size:10px;letter-spacing:1.5px;font-weight:700}
.banner .bx{font-size:12.5px;line-height:1.55;color:var(--text)}
.banner .bx b{color:var(--accent)}
.banner .bb{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:4px}
.banner.review{border-color:var(--accent);background:rgba(0,230,118,.07)}.banner.review .bt{color:var(--accent)}
.banner.dispatch{border-color:var(--purple);background:rgba(176,124,214,.09)}.banner.dispatch .bt{color:var(--purple)}
.banner.answer,.banner.paused{border-color:var(--amber);background:rgba(224,165,60,.08)}.banner.answer .bt,.banner.paused .bt,.banner.run .bt{color:var(--amber)}
.banner.run{border-color:rgba(224,165,60,.5)}
.banner.fail{border-color:var(--red);background:rgba(255,92,92,.07)}.banner.fail .bt{color:var(--red)}
.tbox{margin:0 0 14px}
.timeline-bar{display:flex;height:16px;border-radius:5px;overflow:hidden;gap:2px;background:rgba(0,230,118,.06)}
.ts{min-width:6px;display:flex;align-items:center;justify-content:center;font-size:9px;color:#04160c;overflow:hidden;white-space:nowrap;border-radius:3px}
.ts.done{background:var(--accent)}.ts.running{background:var(--amber)}.ts.fail{background:var(--red)}.ts.proposed{background:rgba(176,124,214,.55)}.ts.wait{background:var(--amber)}
.tleg{font-size:10.5px;color:var(--text-muted);margin-top:5px;line-height:1.6}.tleg b{color:var(--text);font-weight:600}
.trk{font-family:'Orbitron',monospace;font-size:9px;letter-spacing:1.2px;color:var(--text-muted);margin-bottom:5px;display:flex;justify-content:space-between}
.rbox{border:1px solid var(--border-dim);border-radius:9px;background:rgba(8,12,40,.6);overflow:hidden}
.ftabs{display:flex;flex-wrap:wrap;gap:5px;padding:8px;border-bottom:1px solid var(--border-dim)}
.ftab{background:transparent;border:1px solid var(--border-dim);color:var(--text-muted);border-radius:6px;padding:4px 9px;font-size:11.5px;cursor:pointer;font-family:ui-monospace,Consolas,monospace}
.ftab.sel{border-color:var(--accent);color:var(--accent);background:rgba(0,230,118,.1)}
.rmode{display:flex;gap:6px;padding:8px 8px 0}
.rview{padding:12px 14px;max-height:48vh;overflow:auto;font-size:13px;line-height:1.6}
.rview pre{max-height:none;border:0;background:transparent;padding:0;font-size:12px}
.rview h3,.rview h4,.rview h5{color:var(--accent);margin:10px 0 4px}.rview code{background:var(--bg);border:1px solid var(--border-dim);border-radius:4px;padding:0 4px;font-size:11.5px}
.rview .wl{color:var(--blue)}
details.fold{margin-top:18px;border:1px solid var(--border-dim);border-radius:9px;padding:0 12px}
details.fold summary{cursor:pointer;padding:10px 0;font-family:'Orbitron',monospace;font-size:9px;letter-spacing:1.5px;color:var(--text-muted)}
.modal.wide{width:920px}
.pmt{border:1px solid var(--border-dim);border-radius:6px;margin:6px 0;background:rgba(0,0,0,.25)}
.pmt summary{cursor:pointer;padding:6px 10px;font-size:11px;color:var(--amber);font-family:'Orbitron',monospace;letter-spacing:.8px}
.pmt pre{max-height:260px;overflow:auto;white-space:pre-wrap;margin:0;padding:8px 10px;border:0;background:transparent;font-size:11.5px}
.rep{font-family:'Orbitron',monospace;font-size:8px;letter-spacing:1.5px;color:var(--accent);margin:8px 0 2px}
.trh{font-family:'Orbitron',monospace;font-size:9px;letter-spacing:1.2px;color:var(--accent);margin:14px 0 6px;padding-top:8px;border-top:1px solid var(--border-dim)}
.trt{white-space:pre-wrap;border-left:2px solid var(--border-bright);padding:4px 10px;margin:4px 0;font-family:Outfit,sans-serif;font-size:12.5px;color:var(--text);line-height:1.55}
.arch-facts{margin-top:16px;border-top:1px solid var(--border-dim);padding-top:12px}
.arch-facts dt{font-family:'Orbitron',monospace;font-size:9.5px;letter-spacing:1px;color:var(--blue);margin-top:10px}
.arch-facts dd{margin:3px 0 0;font-size:12.5px;color:var(--text-muted);line-height:1.5}
</style></head>
<body>
<div id="toast"></div>
<div class="bar">
  <a class="btn" href="/"><svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>HUB</a>
  <span class="brand">MISSIONS</span>
  <button class="btn go" id="btn-new"><svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>NEW MISSION</button>
  <span class="spacer"></span>
  <a class="btn" href="/agents">AGENTS</a>
  <a class="btn" href="/graph">GRAPH</a>
  <button class="btn" id="btn-arch"><svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9.5"/><path d="M12 11v5.4"/><circle cx="12" cy="7.7" r="1" fill="currentColor" stroke="none"/></svg><span class="lbl">HOW THIS WORKS</span></button>
  __TALK_BUTTON__
  <button class="btn" id="btn-reload" aria-label="Reload" title="Reload"><svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 12a8 8 0 11-2.7-6M20 4v5h-5"/></svg></button>
</div>
<div class="body">
  <div class="list" id="list"></div>
  <div class="detail" id="detail">
    <div class="hollow" id="hollow">Select a mission, or press NEW MISSION.</div>
    <div id="pane" style="display:none;flex:1;display:none;flex-direction:column;min-height:0"></div>
  </div>
</div>
<div class="scrim" id="tr-scrim"></div>
<div class="modal wide" id="tr-modal">
  <h2>FULL TRANSCRIPT — every model call, tool and reply, in order</h2>
  <div class="feed" id="tr-body" style="max-height:64vh"></div>
  <div class="row" style="margin-top:12px"><button class="btn" id="tr-oc" style="display:none">OPEN IN OPENCODE</button><button class="btn" id="tr-close">close</button></div>
</div>
<div class="scrim" id="sk-scrim"></div>
<div class="modal wide" id="sk-modal">
  <h2>SAVE AS A SKILL</h2>
  <div class="note" id="sk-note" style="color:var(--text-muted)"></div>
  <label>NAME</label><input type="text" id="sk-name">
  <label>THE SKILL (edit it if you like)</label><textarea id="sk-md" style="min-height:250px;font-family:ui-monospace,Consolas,monospace;font-size:12px"></textarea>
  <div id="sk-old" style="display:none"><label>CURRENT VERSION WITH THAT NAME</label><pre id="sk-oldpre" style="max-height:200px"></pre></div>
  <div class="row" style="margin-top:12px"><button class="btn go" id="sk-save">SAVE SKILL</button><button class="btn" id="sk-cancel">CANCEL</button></div>
</div>
<div class="scrim" id="arch-scrim"></div>
<div class="modal" id="arch-modal">
  <h2>HOW A MISSION RUNS</h2>
  <div class="flow">
    <div class="st">1 · ASK</div>
    <div class="d">project + brief. Default run type: <b>Orchestrated</b>.</div>
    <div class="arrow">↓</div>
    <div class="st">ORCHESTRATOR</div>
    <div class="d">reads the project, then either asks you (status <b>REPLY</b> — answer on the card) or writes a plan. It writes no code.</div>
    <div class="arrow">↓</div>
    <div class="st">2 · APPROVE</div>
    <div class="d">pipeline appears: steps, who does each, what depends on what. Nothing runs yet.</div>
    <div class="arrow">↓</div>
    <div class="st you">YOU — RUN PIPELINE</div>
    <div class="arrow">↓</div>
    <div class="st">3 · WORKING — STEPS (coder · tester · doc-writer · …)</div>
    <div class="d">run in ONE working copy — independent steps side by side, dependent ones in order; each gets the request, its own brief, and the earlier steps' summaries.</div>
    <div class="arrow">↓</div>
    <div class="st">HUB CHECKS</div>
    <div class="d">no LLM: compile + tests. A failure is handed back to the coder (max 2 fix rounds) before the reviewer sees it.</div>
    <div class="arrow">↓</div>
    <div class="st">REVIEWER → REVIEW</div>
    <div class="arrow">↓</div>
    <div class="st you">4 · YOU — APPLY TO PROJECT or DISCARD</div>
    <div class="d">Nothing touches the real project before this. Click any pipeline node to see that step's brief, result, model and files.</div>
  </div>
  <dl class="arch-facts">
    <dt>WORK TYPE</dt>
    <dd>Software · Marketing &amp; content · Business &amp; operations · Research. Picks which agents the orchestrator may use and which <b>hub checks</b> run (compile+tests for code; placeholders, channel limits, brand “Avoid” list, unrendered designs for content). Tick <b>LLM Wiki</b> to give agents a citable reference library.</dd>
    <dt>REVIEW LOOP</dt>
    <dd>A reviewer/editor that says <code>changes-needed</code> sends its feedback back to the last writer once, then checks and re-review run again.</dd>
    <dt>RUN TYPES</dt>
    <dd><b>Orchestrated</b> (default) plans then runs a pipeline. <b>Direct</b> = one agent, no plan. <b>Team relay</b> = you pick the order. <b>Parallel drafts</b> = same brief, separate copies, keep the best.</dd>
    <dt>RUNTIME / MODEL</dt>
    <dd>OpenCode or Claude Code per mission. Model policy picks the start; OpenCode retries free-tier errors down a fallback chain.</dd>
  </dl>
  <div class="row" style="margin-top:16px"><button class="btn" id="btn-arch-close">close</button></div>
</div>
<script>__ORBS_JS__</script>
<script>
window.__M0 = __M0_JSON__;
const qs = new URLSearchParams(location.search);
let SHOW_ORPH = false;
let SEL = null, MISSIONS = [], PROJECTS = [], AGENTS = [], MODELS = [], PROFILES = {}, poll = null, es = null;
const $ = (id) => document.getElementById(id);
var ICONS = {"send": "<path d=\"M4 12l16-8-6 16-3-7-7-1z\"/>", "chevd": "<path d=\"M6 9l6 6 6-6\"/>", "chevu": "<path d=\"M6 15l6-6 6 6\"/>", "orch": "<circle cx=\"12\" cy=\"12\" r=\"9\"/><circle cx=\"12\" cy=\"12\" r=\"3\" fill=\"currentColor\" stroke=\"none\"/><path d=\"M12 3v4M12 17v4M3 12h4M17 12h4\"/>", "scale": "<path d=\"M12 4v16M6 20h12M5 8h14M5 8l-2 6a3 3 0 006 0zM19 8l-2 6a3 3 0 006 0z\"/>", "plus": "<path d=\"M12 5v14M5 12h14\"/>", "expand": "<path d=\"M9 4H4v5M15 4h5v5M9 20H4v-5M15 20h5v-5\"/>", "shrink": "<path d=\"M4 9h5V4M20 9h-5V4M4 15h5v5M20 15h-5v5\"/>", "back": "<path d=\"M15 5l-7 7 7 7\"/>", "info": "<circle cx=\"12\" cy=\"12\" r=\"9.5\"/><path d=\"M12 11v5.4\"/><circle cx=\"12\" cy=\"7.7\" r=\"1\" fill=\"currentColor\" stroke=\"none\"/>", "folder": "<path d=\"M3 7.5A1.5 1.5 0 014.5 6H9l2 2.5h8.5A1.5 1.5 0 0121 10v8a1.5 1.5 0 01-1.5 1.5h-15A1.5 1.5 0 013 18z\"/>", "clock": "<circle cx=\"12\" cy=\"12\" r=\"9\"/><path d=\"M12 7v5l3.2 2\"/>", "warn": "<path d=\"M12 4l9.2 16H2.8z\"/><path d=\"M12 10v4.2\"/><circle cx=\"12\" cy=\"17\" r=\".9\" fill=\"currentColor\" stroke=\"none\"/>", "inbox": "<path d=\"M4 13l2.4-7h11.2L20 13v5a1 1 0 01-1 1H5a1 1 0 01-1-1z\"/><path d=\"M4 13h4.6l1 2h4.8l1-2H20\"/>", "tool": "<path d=\"M14.6 6.4a4 4 0 00-5.1 5.1L4 17l3 3 5.5-5.5a4 4 0 005.1-5.1l-2.6 2.6-2.4-.6-.6-2.4z\"/>", "chat": "<path d=\"M4 5.5h16v10.5H9.5L5 20v-4H4z\"/>", "x": "<path d=\"M6 6l12 12M18 6L6 18\"/>"};
function ic(n){ return `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[n]||''}</svg>`; }
const esc = (s) => (s==null?'':String(s)).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ago = (t) => { if(!t) return ''; const s=(Date.now()-t*1000)/1000; if(s<60)return Math.round(s)+'s'; if(s<3600)return Math.round(s/60)+'m'; return Math.round(s/3600)+'h'; };
let _tT=null;
function toast(m,k){ const e=$('toast'); if(!e)return; e.textContent=m; e.classList.toggle('err',k==='err'); e.classList.add('show');
  clearTimeout(_tT); _tT=setTimeout(()=>e.classList.remove('show'),4200); }
async function jget(u){ const r=await fetch(u,{cache:'no-store'}); if(!r.ok) throw new Error(await r.text()); return r.json(); }
async function jpost(u,b){ const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
  const t=await r.text(); let j; try{j=JSON.parse(t)}catch(e){j={raw:t}} if(!r.ok) throw new Error(j.raw||t); return j; }

async function boot(){
  if (Array.isArray(window.__M0)) { MISSIONS = window.__M0; renderList(); }          // first frame comes with the page
  await Promise.all([
    jget('/api/projects').then(r=>{ PROJECTS = r.projects || []; }).catch(()=>{}),
    jget('/api/agents').then(a=>{ AGENTS = a.personas || []; MODELS = a.models || []; }).catch(()=>{}),
    jget('/api/profiles').then(r=>{ PROFILES = r.profiles || {}; }).catch(()=>{}),
    loadRecs(),
    refresh()]);
  renderList();
  poll = setInterval(refresh, 2500);
  if (qs.get('open')) select(qs.get('open'));
  else if (qs.get('project') || qs.get('ask')) { newMission(qs.get('project') || ''); const nb = $('nm-brief'); if (nb && qs.get('ask')) nb.value = qs.get('ask'); }
}
async function refresh(){
  try { MISSIONS = (await jget('/api/missions')).missions || []; } catch(e){ return; }
  renderList();
  if (SEL && MISSIONS.some(m=>m.id===SEL)) renderDetail(SEL);
}
const NEEDS = {needs_input:['REPLY','answer','the orchestrator has questions — reply to continue'],
  plan_ready:['APPROVE','dispatch','a plan is ready — edit it, then press RUN PIPELINE'],
  awaiting_review:['REVIEW','review','work is finished — read the result, then APPLY or DISCARD'],
  paused:['RESUME','resume','paused — press RESUME to continue from the interrupted step']};
const SN = {needs_input:'REPLY',plan_ready:'APPROVE',awaiting_review:'REVIEW',paused:'PAUSED',running:'WORKING',queued:'QUEUED',blocked:'BLOCKED',proposed:'PLANNED',failed:'FAILED',timed_out:'TIMED OUT',applied:'APPLIED',discarded:'DISCARDED',orphaned:'RECOVERED'};
const sname = (s) => SN[s] || String(s||'').replace('_',' ').toUpperCase();
const ACTIVE = ['running','queued','blocked','proposed'];
let HIST_OPEN = false;
function renderList(){
  const keepTop = $('list').scrollTop;
  const orph = MISSIONS.filter(m=>m.status==='orphaned');
  const byNew = (x,y)=>(y.created||0)-(x.created||0);
  const needs = MISSIONS.filter(m=>NEEDS[m.status]).sort(byNew);
  const running = MISSIONS.filter(m=>ACTIVE.includes(m.status)).sort(byNew);
  const hist = MISSIONS.filter(m=>!NEEDS[m.status] && !ACTIVE.includes(m.status) && m.status!=='orphaned').sort(byNew);
  let html = '';
  html += `<div class="sect needs">INBOX <span class="n">${needs.length}</span></div>`;
  html += needs.length ? '<div class="cards">' + needs.map(m=>card(m,false)).join('') + '</div>' : '<div class="listhelp">Inbox zero — nothing is waiting for you.</div>';
  if(running.length){ html += `<div class="sect run">ACTIVE <span class="n">${running.length}</span><small>agents at work</small></div>` + '<div class="cards">' + running.map(m=>card(m,false)).join('') + '</div>'; }
  html += `<div class="sect hist" id="hist-toggle">${HIST_OPEN?'▾':'▸'} ARCHIVE <span class="n">${hist.length}</span><small>${HIST_OPEN?'click to hide':'applied, discarded, failed — click to show'}</small></div>`;
  if(HIST_OPEN) html += '<div class="cards">' + hist.map(m=>card(m,false)).join('') + '</div>';
  if(orph.length && HIST_OPEN) html += `<div class="listhelp" id="orph-toggle" style="cursor:pointer">${SHOW_ORPH?'▾':'▸'} ${orph.length} old working cop${orph.length===1?'y':'ies'} on disk with no record — click to ${SHOW_ORPH?'hide':'show'}</div>` + (SHOW_ORPH ? '<div class="cards">' + orph.map(m=>card(m,false)).join('') + '</div>' : '');
  $('list').innerHTML = `<div class="mhead"><span class="mtitle">MATRIX</span><span class="info" tabindex="0"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-label="How MATRIX works"><circle cx="12" cy="12" r="9.5"/><path d="M12 11v5.4"/><circle cx="12" cy="7.7" r="1" fill="currentColor" stroke="none"/></svg><span class="tip"><div class="th">HOW AN ASK MOVES THROUGH MATRIX</div><ol><li><i>1</i><span><b>ASK</b> — you pick a project and describe the job.</span></li><li class="you"><i>2</i><span><b>REPLY</b> — only if it is unclear: the orchestrator asks up to 3 questions. Nothing has run yet.</span></li><li class="you"><i>3</i><span><b>APPROVE</b> — it shows a plan: steps, agents, order. Edit it, then press RUN PIPELINE.</span></li><li><i>4</i><span><b>WORKING</b> — agents do the steps. Independent steps are decided together; model calls are metered (a local model takes one at a time, cloud a few). Then the hub checks the result.</span></li><li class="you"><i>5</i><span><b>REVIEW</b> — read the result, then APPLY it to your project or DISCARD it.</span></li></ol><div class="tf">Amber steps are your turn. <b>INBOX</b> = waiting on you · <b>ACTIVE</b> = agents at work · <b>ARCHIVE</b> = finished or stopped.</div></span></span><span class="msub">${MISSIONS.filter(m=>m.status!=='orphaned').length} asks</span></div>` + html;
  $('list').scrollTop = keepTop;
  $('hist-toggle').onclick = () => { HIST_OPEN = !HIST_OPEN; renderList(); };
  const ot = $('orph-toggle'); if(ot) ot.onclick = () => { SHOW_ORPH = !SHOW_ORPH; renderList(); };
  document.querySelectorAll('#list .card').forEach(el => el.onclick = () => select(el.dataset.id));
}
function strip(m){
  if(m.kind==='orchestrator'){
    const st = m.status, live = st==='running';
    // a step can only be "running" while the mission is: otherwise the run was interrupted (never blink for a dead run)
    const eff = (s) => (!live && (s==='running'||s==='queued')) ? (s==='running' ? 'failed' : 'proposed') : s;
    const oc = live && !(m.plan||[]).length ? 'running' : st==='needs_input' ? 'proposed' : ((m.plan||[]).length || st==='awaiting_review') ? 'done' : 'failed';
    const orch = `<span class="pd ${oc}"><i></i>orchestrator</span>`;
    const steps = (m.plan||[]).map(x=>`<span class="ar">›</span><span class="pd ${eff(x.status)}"><i></i>${esc(x.agent)}</span>`).join('');
    return `<div class="pstrip">${orch}${steps}</div>`;
  }
  const label = (m.kind==='team' && (m.agents||[]).length) ? m.agents.join(' → ') : m.agent;
  return `<div class="pstrip"><span>${esc(label)}</span><span class="pill">${esc(m.kind)}</span></div>`;
}
function cardTime(m){ return m.work_secs ? `<span title="time the agents actually worked">${ic('clock')}${fmtS(m.work_secs)}</span>` : ''; }
function cardModels(m){
  const mods = (m.models_used && m.models_used.length ? m.models_used : (m.model ? [m.model] : [])).map(x=>x.replace(/^(opencode|ollama)\//,''));
  if(!mods.length) return '';
  if(mods.length===1) return `<span>${esc(mods[0])}</span>`;
  return `<span title="${esc(mods.join(', '))}">${mods.length} models: ${esc(mods.map(x=>x.split(':')[0]).join(' + '))}</span>`;
}
let EXP = null;
window.__voiceCtx = () => ({mission: SEL});          // the conversation bot is told which ask is open
const ORB_FOR = {orchestrator:'solving', coder:'working', tester:'working', 'data-analyst':'working', designer:'working', 'doc-writer':'composing', copywriter:'composing',
  'ops-writer':'composing', 'product-manager':'composing', 'project-manager':'composing', analyst:'searching', researcher:'searching', reviewer:'weaving', editor:'weaving',
  'compliance-reviewer':'weaving', gate:'connecting'};
const orb = (state, size) => `<canvas class="orb" data-orb="${state}" data-size="${size||20}"></canvas>`;
const orbFor = (agent) => ORB_FOR[agent] || 'working';
function mountOrbs(root){ try{ if(window.ThinkingOrbs) window.ThinkingOrbs.mountAll(root||document, '#00e676'); }catch(e){} }
function deep(m){
  const rows = (m.plan||[]).map(x=>{
    const live = m.status==='running', stt = (!live && (x.status==='running'||x.status==='queued')) ? 'proposed' : x.status;
    const dot = stt==='done' ? 'awaiting_review' : stt==='running' ? 'running' : stt==='failed' ? 'failed' : 'proposed';
    const t = (x.started && x.ended) ? fmtS(x.ended - x.started) : '';
    const sm = String(x.summary || x.note || '').split('\n')[0].slice(0,120);
    return `<div class="dstep"><span class="dot ${dot}"></span><b>${esc(x.agent)}</b><span class="dm">${esc(shortM(stepModel(m,x)[0]))}</span><span class="dm">${t}</span>${sm?`<div class="dt">${esc(sm)}</div>`:''}</div>`;
  }).join('');
  const bits = [];
  if(m.verify) bits.push(`<span>${ic('scale')}hub checks ${m.verify.ok?'passed':'FAILED'}</span>`);
  if(m.changed) bits.push(`<span>${m.changed} file${m.changed>1?'s':''} changed</span>`);
  if(m.work_secs) bits.push(`<span>${ic('clock')}${fmtS(m.work_secs)}</span>`);
  if(m.autonomy && m.autonomy!=='plan') bits.push(`<span>${esc(AUTONOMY[m.autonomy])}</span>`);
  const warn = m.error ? `<div class="dline" style="color:var(--red)">${ic('warn')}${esc(m.error.slice(0,140))}</div>` : (m.model_note ? `<div class="dline" style="color:var(--amber)">${ic('warn')}${esc(m.model_note)}</div>` : '');
  return `<div class="deep">${rows}${bits.length?`<div class="dline">${bits.join('')}</div>`:''}${warn}<div class="dhint">the full thread is open on the right</div></div>`;
}
const AUTONOMY = {ask:'ASK FIRST', plan:'PLAN, THEN WAIT', auto:'RUN & REVIEW'};
function card(m,child){
  const prof = (m.profile && m.profile!=='code') ? `<span class="pill">${esc((PROFILES[m.profile]||{}).label||m.profile)}</span>` : '';
  const need = NEEDS[m.status], open = EXP===m.id && m.id===SEL;
  const dotCls = m.status==='running' ? 'running' : m.status;
  return `<div class="card ${child?'child':''} ${need?'needs':''} ${m.id===SEL?'sel':''} ${open?'open':''}" data-id="${m.id}" title="${need?esc(need[2]):''}">
    <div class="pj">${ic('folder')}${esc(m.project_name)}</div>
    <div class="top"><span class="dot ${dotCls}"></span>${need?`<span class="tag-act tag-${need[1]}">${need[0]}</span>`:`<span style="font-size:10.5px;color:var(--text-muted);letter-spacing:.4px">${esc(sname(m.status))}</span>`}${prof}${m.runtime==='claude-code'?'<span class="pill">claude</span>':''}<span class="spacer"></span>
      <span style="font-size:10px;color:var(--text-faint)">${ago(m.created)}</span><span class="chev">${ic(open?'chevu':'chevd')}</span></div>
    <div class="asktxt">${esc(m.brief)}</div>
    ${open ? deep(m) : `<div class="mt">${m.changed?`<span>${m.changed} file${m.changed>1?'s':''}</span>`:''}${cardTime(m)}${cardModels(m)}</div>`}
  </div>`;
}
function showDetail(on){ const b = document.querySelector('.body'); if(b) b.classList.toggle('m-detail', !!on); if(on && window.scrollTo) window.scrollTo(0,0); }
function select(id){ if(SEL===id && window.innerWidth>720){ EXP = (EXP===id) ? null : id; renderList(); return; }     // 2nd click on the open card folds it
  SEL=id; EXP=id; showDetail(true); renderList(); renderDetail(id); if(es){es.close();es=null;} const m=MISSIONS.find(x=>x.id===id);
  if(window.HubVoice) HubVoice.contextChanged(id);
  if(m && m.status==='running'){ es=new EventSource('/api/missions/'+id+'/events'); es.onmessage=()=>renderDetail(id); } }


const PIPEOPEN = {};
const DOWN = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
function repeatBlock(d){
  if(d.kind!=='orchestrator' || !['awaiting_review','applied'].includes(d.status)) return '';
  const sc = d.schedule;
  const body = sc
    ? `<div class="tnote" style="color:#d9ffe9;font-size:12.5px">Repeats <b>${esc(sc.text)}</b>. It starts by itself, runs its plan, then waits in your INBOX at REVIEW. Nothing is applied or sent automatically.</div><div class="row" style="margin-top:8px"><button class="btn stop" id="m-unrepeat" data-sid="${esc(sc.id)}">STOP REPEATING</button></div>`
    : `<div class="row" style="align-items:center"><select id="rp-every" style="width:auto"><option value="weekly">every week on</option><option value="daily">every day</option><option value="monthly">every month on day</option></select>
        <select id="rp-dow" style="width:auto">${DOWN.map((n,i)=>`<option value="${i}">${n}</option>`).join('')}</select><input type="number" id="rp-dom" min="1" max="28" value="1" style="width:70px;display:none">
        <input type="time" id="rp-at" value="09:00" style="width:auto"><button class="btn go" id="m-repeat">REPEAT THIS</button></div>
        <div class="tnote">It starts by itself and runs its plan, then waits at REVIEW. You still decide what is applied.</div>`;
  return `<div class="tbot"><div class="twho">${ic('clock')}REPEAT THIS?</div><div class="tblk">${body}</div></div>`;
}
function skillBlock(d){
  if(!['awaiting_review','applied'].includes(d.status)) return '';
  return `<div class="tbot"><div class="twho">${ic('scale')}SAVE THIS AS A SKILL?<span class="tm2">the model drafts it, you read and approve it</span></div><div class="tblk"><div class="tnote" style="color:#d9ffe9;font-size:12.5px">Turn what worked here (limits, formats, steps) into a reusable skill for next time. Nothing is saved until you press SAVE, and an existing skill is never replaced without showing you both versions.</div><div class="row" style="margin-top:8px"><button class="btn" id="m-skill">DRAFT A SKILL FROM THIS ASK</button></div></div></div>`;
}
let SKILL = null;
async function draftSkill(d){
  toast('Drafting a skill… (one model call)');
  try { SKILL = await jpost('/api/missions/'+d.id+'/skill-draft', {}); } catch(e){ toast('Could not draft: '+e.message, 'err'); return; }
  $('sk-name').value = SKILL.name; $('sk-md').value = SKILL.markdown; SKILL.replace = false;
  $('sk-old').style.display = SKILL.exists ? 'block' : 'none'; if(SKILL.exists) $('sk-oldpre').textContent = SKILL.existing;
  $('sk-note').textContent = SKILL.exists ? 'A skill with this name already exists. Its current text is below; saving replaces it only after you press REPLACE.' : 'Edit anything you like, then save.';
  $('sk-save').textContent = SKILL.exists ? 'REPLACE EXISTING SKILL' : 'SAVE SKILL';
  $('sk-scrim').classList.add('open'); $('sk-modal').classList.add('open');
}
async function saveSkill(){
  const body = {name: $('sk-name').value.trim(), markdown: $('sk-md').value, overwrite: !!(SKILL && SKILL.exists)};
  const r = await fetch('/api/skills/save', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  const j = await r.json().catch(()=>({}));
  if(r.status===409){ SKILL = Object.assign(SKILL||{}, {exists:true, existing:j.existing}); $('sk-old').style.display='block'; $('sk-oldpre').textContent=j.existing; $('sk-note').textContent='That name is taken. Read the current version below; press REPLACE to overwrite it.'; $('sk-save').textContent='REPLACE EXISTING SKILL'; return; }
  if(!r.ok){ toast('Not saved: '+(j.raw||j.error||r.statusText),'err'); return; }
  $('sk-scrim').classList.remove('open'); $('sk-modal').classList.remove('open'); toast('Skill saved: '+body.name);
}
const JLAB = {checks_ok:'Hub checks passed', has_output:'The run produced files', reviewer_verdict:'Reviewer verdict', claims_supported:'Every claim is supported by the brief'};
const bot = (who, inner) => `<div class="tbot"><div class="twho">${who}</div><div class="tblk">${inner}</div></div>`;
function askBubble(d){
  const first = (d.brief||'').split('\n---')[0].trim().slice(0,600);
  return `<div class="tmsg me">${esc(first)}</div>`;
}
function answersBubble(d){ return (d.answers||[]).length ? `<div class="tmsg me">${d.answers.map(a=>esc(a.a)).join(' · ')}</div>` : ''; }
function workBlock(d){
  if(d.kind!=='orchestrator' || !(d.plan||[]).length || ['needs_input','plan_ready'].includes(d.status)) return '';
  const os = ownerSecs(d), live = d.status==='running';
  const rows = (d.plan||[]).map(x=>{
    const stt = (!live && (x.status==='running'||x.status==='queued')) ? 'failed' : x.status;
    const pct = stt==='done' ? 100 : stt==='running' ? 60 : stt==='failed' ? 100 : 0, cls = stt==='running' ? 'run' : stt==='failed' ? 'bad' : '';
    const t = os[x.id], em = stepModel(d,x)[0];
    return `<div class="tact"><span class="tag2">${stt==='running'?orb(orbFor(x.agent),20):'<span class="orbgap"></span>'}${esc(x.agent)}</span><span class="tbar2"><i class="${cls}" style="width:${pct}%"></i></span><span class="tm2">${t?fmtS(t):(stt==='queued'?'queued':'')}</span><span class="tmod" title="${esc(em)}">${esc(shortM(em))}</span></div>`;
  }).join('');
  const gate = d.verify ? `<div class="tact"><span class="tag2"><span class="orbgap"></span>hub checks</span><span class="tbar2"><i class="${d.verify.ok?'':'bad'}" style="width:100%"></i></span><span class="tm2">${os.gate?fmtS(os.gate):''}</span><span class="tmod">no LLM</span></div>` : '';
  const head = live ? `${orb('working',20)}WORKING` : `${ic('orch')}WORKED`;
  return `<div class="tbot"><div class="twho">${head}<span class="tm2">${live?'live, from the mission events':'per step'} · model calls are queued to suit the model</span></div><div class="tblk">${rows}${gate}</div></div>`;
}
function judgeBlock(d){
  const j = d.judge; if(!j || !['awaiting_review','applied','failed','timed_out'].includes(d.status)) return '';
  const rows = j.results.map(r=>{
    const lab = JLAB[r.id] || (j.questions||{})[r.id] || r.id;
    if(r.answer==null) return `<div class="tjrow"><span>${esc(lab)}</span><span class="tbar2"></span><span class="tp mut">not checked</span><span class="tsrc">${r.id==='claims_supported' ? `<button class="btn" id="m-judge">${ic('scale')}CHECK NOW</button>` : ''}</span></div>`;
    const good = r.id==='reviewer_verdict' ? r.answer==='ship' : r.answer==='yes', warn = r.id==='reviewer_verdict' && r.answer==='changes-needed';
    const col = good ? '' : (warn ? 'w' : 'b'), w = r.p==null ? 100 : Math.round(r.p*100);
    const val = r.backend==='rules' ? r.answer : (r.answer + (r.p!=null ? ' '+r.p.toFixed(2) : ' · confidence unknown'));
    return `<div class="tjrow"><span>${esc(lab)}</span><span class="tbar2"><i class="${col}" style="width:${w}%"></i></span><span class="tp ${col}">${esc(val)}</span><span class="tsrc">${r.backend==='rules'?'rules':'local model'}</span></div>`;
  }).join('');
  const rt = j.route || {}, why = (rt.route==='human' && (rt.reasons||[]).length) ? `Flagged for you: ${rt.reasons.map(esc).join('; ')}.` : 'Nothing flagged. Your APPLY or DISCARD is logged next to these answers, so we can measure how often they agree with you.';
  return `<div class="tbot"><div class="twho">${ic('scale')}INDEPENDENT CHECK<span class="tm2">not the writer's opinion of itself</span></div><div class="tblk">${rows}<div class="tnote">${why}</div></div></div>`;
}
function pipeFold(d, dflt){
  const open = PIPEOPEN[d.id]!=null ? PIPEOPEN[d.id] : dflt;
  return `<details class="tfold" ${open?'open':''} ontoggle="PIPEOPEN['${d.id}']=this.open;fitPipe()"><summary>PIPELINE — who did what, in what order</summary>${pipelineBlock(d)}</details>`;
}
function threadBody(d){
  const st = d.status;
  let h = askBubble(d);
  if(st==='needs_input') return h + bot(`${orb('breathing',20)}ORCHESTRATOR<span class="tm2">has questions for you</span>`, actionBanner(d) + pipelineBlock(d));
  h += answersBubble(d);
  if(st==='plan_ready') return h + bot(`${ic('orch')}ORCHESTRATOR<span class="tm2">plan · nothing has run yet</span>`, actionBanner(d) + pipelineBlock(d));
  if(st==='running' || st==='queued' || st==='blocked'){
    const hero = (d.plan||[]).find(s=>s.status==='running');
    return h + bot(`${orb(hero?orbFor(hero.agent):'solving',20)}${hero?esc(hero.agent.toUpperCase()):'ORCHESTRATOR'}<span class="tm2">${hero?'working now':'planning'}</span>`, `<div style="display:flex;gap:16px;align-items:center"><div style="flex:none">${orb(hero?orbFor(hero.agent):'solving',64)}</div><div style="flex:1;min-width:0">${actionBanner(d)}</div></div>`) + workBlock(d) + pipeFold(d, true);
  }
  const who = st==='awaiting_review' ? `${ic('orch')}REVIEW<span class="tm2">YOUR TURN · nothing has touched the project</span>` : `${ic('orch')}${esc(sname(st))}`;
  return h + workBlock(d) + judgeBlock(d) + bot(who, actionBanner(d) + resultBlock(d)) + repeatBlock(d) + skillBlock(d) + pipeFold(d, false) + (d.kind==='orchestrator' && d.children.length ? planBlock(d) : '') + checksBlock(d);
}
function tbarHtml(d){
  const ph = {needs_input:'Answer with the options above, or type /defaults', plan_ready:'Type /run to start the pipeline, or edit a step first', running:'Agents are working. Type /pause to stop',
    awaiting_review:'Describe what should change, or /apply · /discard', paused:'Type /resume to continue', failed:'Type /resume or /retry'}[d.status] || 'Start a follow-up ask about this project…';
  return `<div class="tbar"><div class="tin">${ic('send')}<input id="t-in" type="text" autocomplete="off" placeholder="${esc(ph)}"><span class="tkey">Enter</span></div><div class="tslash">/run · /pause · /resume · /apply · /discard · /retry · /status · /defaults · /changes text</div></div>`;
}
function tSend(d){
  const el = $('t-in'); const v = (el.value||'').trim(); if(!v) return; el.value = '';
  const click = (id) => { const b = $(id); if(b) b.click(); else toast('Not available while '+sname(d.status).toLowerCase(), 'err'); };
  if(v[0]==='/'){
    const parts = v.slice(1).split(/\s+/), c = parts.shift(), arg = parts.join(' ');
    const cmds = {run:()=>click('m-runplan'), pause:()=>click('m-abort'), abort:()=>click('m-abort'), resume:()=>click('m-resume'), apply:()=>click('m-apply'), discard:()=>click('m-discard'), retry:()=>click('m-retry'), defaults:()=>click('m-answer-def'),
      status:()=>toast(sname(d.status)+' · '+(d.plan||[]).filter(x=>x.status==='done').length+'/'+(d.plan||[]).length+' steps · '+fmtS(totalSecs(d))),
      changes:()=>arg ? jpost('/api/missions/'+d.id+'/continue',{message:arg}).then(refresh) : toast('/changes needs a message','err')};
    (cmds[c] || (()=>toast('Unknown command /'+c,'err')))(); return;
  }
  if(d.status==='awaiting_review') return jpost('/api/missions/'+d.id+'/continue',{message:v}).then(refresh).catch(e=>toast(e.message,'err'));
  if(['applied','discarded','failed','timed_out','orphaned'].includes(d.status)){ newMission(d.project_slug); const t = $('nm-brief'); if(t) t.value = v; return; }
  if(window.HubVoice) return HubVoice.ask(v);            // anything else is a question for the conversation bot
  toast('Not now: '+sname(d.status).toLowerCase()+'. Try /status','err');
}

async function renderDetail(id){
  let d; try { d = await jget('/api/missions/'+id); } catch(e){ return; }
  // a waiting card has inputs: don't rebuild it under the user's hands every poll
  const sig = d.status+'|'+(d.plan||[]).map(x=>x.status).join(',')+'|'+(d.answers||[]).length;
  const evs0 = d.events||[];
  const full = sig+'|'+evs0.length+'|'+JSON.stringify(evs0[evs0.length-1]||'')+'|'+(d.changed_files||[]).length+'|'+(d.verify?d.verify.ok+''+d.verify.attempts:'')+'|'+(PSEL[id]||'')+'|'+(d.model||'')+'|'+(d.error||'');
  const same = $('pane').dataset.mid===id;
  if(same && $('pane').dataset.full===full) return;                    // nothing changed: leave the page (and your scroll position) alone
  if((d.status==='needs_input'||d.status==='plan_ready') && same && $('pane').dataset.sig===sig && $('pane').dataset.full!=='') { $('pane').dataset.full=full; return; }
  const sc0 = same ? $('pane').querySelector('.dscroll') : null, keepTop = sc0 ? sc0.scrollTop : 0;
  const f0 = same ? $('mfeed') : null, feedPinned = !f0 || (f0.scrollTop + f0.clientHeight >= f0.scrollHeight - 30), feedTop = f0 ? f0.scrollTop : 0;
  $('pane').dataset.mid=id; $('pane').dataset.sig=sig; $('pane').dataset.full=full;
  $('hollow').style.display='none'; $('pane').style.display='flex';
  const pl = (d.plan||[]).length, secs = totalSecs(d);
  $('pane').innerHTML = `
    <div class="dhead">
      <button class="btn backbtn" id="m-back">${ic('back')}ALL ASKS</button>
      <h1 class="asktitle">${esc((d.brief||'').split('\n')[0].slice(0,160))}</h1>
      <div class="sub">
        <span class="pill">${ic('folder')}${esc(d.project_name)}</span>
        <span class="pill">${esc(sname(d.status))}</span>
        ${d.profile&&d.profile!=='code'?`<span class="pill">${esc((PROFILES[d.profile]||{}).label||d.profile)}</span>`:''}${d.reference?'<span class="pill">wiki ref</span>':''}${d.runtime==='claude-code'?'<span class="pill">claude</span>':''}
        ${d.autonomy&&d.autonomy!=='plan'?`<span class="pill">${esc(AUTONOMY[d.autonomy])}</span>`:''}
        ${d.model?`<span>${esc(d.model.replace('opencode/','').replace('ollama/',''))}</span>`:''}
        <span>${ago(d.created)} ago</span>${secs?`<span>agents worked ${fmtS(secs)}</span>`:''}
        <button class="btn" onclick="mTranscript('${d.id}')">FULL TRANSCRIPT</button>
      </div>
    </div>
    <div class="dscroll">
      ${d.model_note?`<div class="note" style="margin:0 0 12px">${ic('warn')}${esc(d.model_note)}</div>`:''}
      ${threadBody(d)}
      <details class="fold"><summary>WORKING COPY &amp; RAW ACTIVITY FEED</summary>
        <div style="font-size:11px;font-family:ui-monospace,Consolas,monospace;color:var(--text-muted);word-break:break-all;-webkit-user-select:all;user-select:all;margin-top:4px">${esc(d.worktree||'—')}</div>
        <div class="row" style="margin:6px 0 10px"><button class="btn" id="m-folder">OPEN FOLDER</button>
          <button class="btn" onclick="navigator.clipboard.writeText('${esc(d.worktree)}')">COPY PATH</button>
          <span style="font-size:10.5px;color:var(--text-faint)">kept until you APPLY or DISCARD</span></div>
        <div class="feed" id="mfeed" style="margin-bottom:12px">${(d.events||[]).map(feedRow).join('') || '<span style="color:var(--text-faint)">no events yet</span>'}</div>
      </details>
    </div>
    ${tbarHtml(d)}`;
  const f = $('mfeed'); if(f) f.scrollTop = feedPinned ? f.scrollHeight : feedTop;
  const sc1 = $('pane').querySelector('.dscroll'); if(sc1) sc1.scrollTop = keepTop;
  bindPipeline(d);
  bindActions(d);
  loadNodeRows(d);
  loadResult(d);
  fitPipe();
  mountOrbs($('pane'));
}
function bindActions(d){
  const fb = (MODELS.find(x=>x.local)||MODELS.find(x=>/ultra/i.test(x.id))||{}).id || '';
  const on = (id, fn) => { const e = $(id); if(e) e.onclick = fn; };
  const go = (p, b) => jpost('/api/missions/'+d.id+'/'+p, b||{});
  on('m-apply', async () => {
    try { const r = await go('apply');
      toast(r.note || (r.ok ? 'Applied — merged into '+d.project_name : ('Not merged: '+(r.run_this||r.reason||'see server log'))), r.ok?'':'err');
    } catch(e){ toast('Apply failed: '+e.message,'err'); }
    refresh(); });
  on('m-folder', async () => { try { const r = await go('folder'); toast('Opened '+r.path); } catch(e){ toast('Could not open folder: '+e.message,'err'); } });
  on('m-discard', async () => { if(!confirm('Stop this ask and delete its working copy? The row stays as history.')) return; await go('discard'); refresh(); });
  on('m-forget', async () => { await go('forget'); SEL=null; $('pane').style.display='none'; $('hollow').style.display='flex'; refresh(); });
  on('m-abort', () => go('abort').then(refresh));
  on('m-retry', async () => { const r = await go('retry'); select(r.id); });
  on('m-retryfb', async () => { const r = await go('retry', {model:fb}); select(r.id); });
  on('m-continue', async () => { const msg = prompt('What should change? (sent to the agents as a follow-up)'); if(!msg) return; await go('continue', {message:msg}); refresh(); });
  on('m-resume', async () => { try { await go('resume'); } catch(e){ toast(e.message,'err'); } refresh(); select(d.id); });
  const bk = $('m-back'); if(bk) bk.onclick = () => { showDetail(false); };
  const ti = $('t-in'); if(ti) ti.onkeydown = (e) => { if(e.key==='Enter') tSend(d); };
  const ev = $('rp-every'); if(ev) ev.onchange = () => { $('rp-dow').style.display = ev.value==='weekly' ? '' : 'none'; $('rp-dom').style.display = ev.value==='monthly' ? '' : 'none'; };
  on('m-repeat', async () => { try { await jpost('/api/missions/'+d.id+'/repeat', {every:$('rp-every').value, at:$('rp-at').value||'09:00', dow:+$('rp-dow').value, dom:+$('rp-dom').value||1}); toast('Repeat saved'); } catch(e){ toast(e.message,'err'); } $('pane').dataset.full=''; renderDetail(d.id); });
  on('m-unrepeat', async () => { await fetch('/api/schedules/'+$('m-unrepeat').dataset.sid, {method:'DELETE'}); toast('Stopped repeating'); $('pane').dataset.full=''; renderDetail(d.id); });
  on('m-skill', () => draftSkill(d));
  on('m-judge', async () => { const b = $('m-judge'); if(b) b.disabled = true; toast('Asking the local model… (one call)');
    try { await go('judge'); } catch(e){ toast('Check failed: '+e.message,'err'); } $('pane').dataset.full = ''; renderDetail(d.id); });
  document.querySelectorAll('[data-oc]').forEach(b => b.onclick = () => openOC(d.id, b.dataset.oc));
  document.querySelectorAll('[data-resume]').forEach(b => b.onclick = async () => {
    try { await go('resume', {from_step:b.dataset.resume}); } catch(e){ toast(e.message,'err'); } refresh(); select(d.id); });
  document.querySelectorAll('.ftab').forEach(b => b.onclick = () => { const sel = RSEL[d.id] = RSEL[d.id] || {}; sel.path = b.dataset.p;
    document.querySelectorAll('.ftab').forEach(x => x.classList.toggle('sel', x===b)); loadResult(d); });
  document.querySelectorAll('.rmode [data-m]').forEach(b => b.onclick = () => { const sel = RSEL[d.id] = RSEL[d.id] || {}; sel.mode = b.dataset.m;
    document.querySelectorAll('.rmode [data-m]').forEach(x => x.classList.toggle('sel', x===b)); loadResult(d); });
}
const RSEL = {};
function actionBanner(d){
  const n = (d.plan||[]).length, os = ownerSecs(d), t = totalSecs(d), st = d.status;
  const fb = (MODELS.find(x=>x.local)||{}).id || '';
  const done = (d.plan||[]).filter(s=>s.status==='done').length;
  const cur = (d.plan||[]).find(s=>s.status==='running');
  const b = (id, cls, txt) => `<button class="btn ${cls||''}" id="${id}">${txt}</button>`;
  let cls='', title='', text='', btns='';
  if(st==='needs_input'){ cls='answer'; title='YOUR TURN · REPLY';
    text=`The orchestrator needs ${d.questions.length} answer${d.questions.length>1?'s':''} before it can plan. Nothing has been planned or run yet. Answer in the yellow card below, or take the ★ defaults.`; btns=b('m-discard','stop','DISCARD'); }
  else if(st==='plan_ready'){ cls='dispatch'; title='YOUR TURN · APPROVE';
    text=`The orchestrator finished planning in <b>${os.orch ? fmtS(os.orch) : 'a few seconds'}</b>: <b>${n} step${n===1?'':'s'}</b>. <b>Nothing has run yet</b> — RUN PIPELINE is what starts the agents. Read the pipeline below (click a step to change its agent, model or instructions), then press RUN PIPELINE.`;
    btns=b('m-runplan','go',`RUN PIPELINE (${n} steps)`)+`<label class="ck" style="display:inline-flex;margin:0"><input type="checkbox" id="m-usesug"> use the suggested model per agent</label>`+b('m-discard','stop','DISCARD'); }
  else if(st==='awaiting_review'){ cls='review'; title='YOUR TURN · REVIEW';
    text=`Finished in <b>${fmtS(t)}</b>${d.verify?` · hub checks ${d.verify.ok?'passed ✓':'failed ✗'}`:''}. Read the <b>result</b> below. <b>APPLY TO PROJECT</b> merges the ${d.changed} file${d.changed===1?'':'s'} into <b>${esc(d.project_name)}</b>; <b>DISCARD</b> throws the work away. Nothing has touched your project yet.`;
    btns=b('m-apply','go','APPLY TO PROJECT')+b('m-discard','stop','DISCARD')+b('m-continue','','ASK FOR CHANGES…'); }
  else if(st==='paused'){ cls='paused'; title='PAUSED';
    text=`${esc(d.error||'')} Finished steps are kept. RESUME re-runs the interrupted step and carries on; or open any step and press RE-RUN FROM THIS STEP.`; btns=b('m-resume','go','RESUME')+b('m-discard','stop','DISCARD'); }
  else if(st==='running'){ cls='run';
    title = cur ? `WORKING · step ${done+1} of ${n}: ${cur.agent}` : (n ? 'WORKING · hub checks / review' : 'WORKING · the orchestrator is planning');
    text='Nothing needs you right now. The bar and dots update live; click a step to read its transcript as it happens.'; btns=b('m-abort','stop',(d.kind==='orchestrator'&&n)?'PAUSE':'ABORT'); }
  else if(st==='failed'||st==='timed_out'){ cls='fail'; title='STOPPED · '+sname(st);
    text=esc(d.error||'The run stopped.'); btns=((n&&d.kind==='orchestrator')?b('m-resume','go','RESUME'):'')+b('m-retry','','RETRY')+(fb?b('m-retryfb','',`RETRY ON ${esc(fb)}`):'')+b('m-discard','stop','DISCARD')+b('m-forget','','CLEAR'); }
  else { cls='done'; title = st==='orphaned' ? 'RECOVERED FROM DISK' : sname(st);
    text = st==='applied' ? `Merged into ${esc(d.project_name)}.` : (st==='orphaned' ? 'An old working copy found on disk with no record.' : '');
    btns = (st==='orphaned'?b('m-apply','go','APPLY TO PROJECT')+b('m-discard','stop','DISCARD'):'')+b('m-forget','','CLEAR'); }
  return `<div class="banner ${cls}"><div class="bt">${title}</div><div class="bx">${text}</div><div class="bb">${btns}</div></div>`;
}
function resultBlock(d){
  const files = (d.changed_files||[]).filter(f=>!/^shared\//.test(f.path));
  if(!files.length){
    return (d.status==='awaiting_review'||d.status==='applied') ? '<h2>Result</h2><div class="note" style="color:var(--text-muted)">No project files were changed.</div>' : '';
  }
  let sel = RSEL[d.id];
  if(!sel || !files.some(f=>f.path===sel.path)) sel = RSEL[d.id] = {path: files[0].path, mode: 'content'};
  if(!sel.mode) sel.mode = 'content';
  return `<h2>Result — what the agents produced <span style="color:var(--text-muted)">${files.length} file${files.length===1?'':'s'}</span></h2>
    <div class="rbox"><div class="ftabs">${files.map(f=>`<button class="ftab ${f.path===sel.path?'sel':''}" data-p="${esc(f.path)}"><span style="color:var(--amber)">${esc(f.status)}</span> ${esc(f.path)}</button>`).join('')}</div>
      <div class="rmode"><button class="btn ${sel.mode==='content'?'sel':''}" data-m="content">CONTENT</button><button class="btn ${sel.mode==='diff'?'sel':''}" data-m="diff">DIFF</button></div>
      <div class="rview" id="rview">loading…</div></div>`;
}
function mdLite(t){
  let h = esc(t);
  h = h.replace(/^### (.*)$/gm,'<h5>$1</h5>').replace(/^## (.*)$/gm,'<h4>$1</h4>').replace(/^# (.*)$/gm,'<h3>$1</h3>')
       .replace(/\*\*([^*\n]+)\*\*/g,'<b>$1</b>').replace(/`([^`\n]+)`/g,'<code>$1</code>').replace(/^\s*[-*] (.*)$/gm,'• $1')
       .replace(/\[\[([^\]]+)\]\]/g,'<span class="wl">[[$1]]</span>');
  return '<div style="white-space:pre-wrap">'+h+'</div>';
}
async function loadResult(d){
  const box = $('rview'); const sel = RSEL[d.id]; if(!box || !sel) return;
  try{
    if(sel.mode==='diff'){
      const t = await (await fetch('/api/missions/'+d.id+'/diff?path='+encodeURIComponent(sel.path))).text();
      box.innerHTML = '<pre>'+t.split('\n').map(l=>`<div class="${l.startsWith('+')&&!l.startsWith('+++')?'diff-add':(l.startsWith('-')&&!l.startsWith('---')?'diff-del':'')}">${esc(l)}</div>`).join('')+'</pre>';
      return;
    }
    const j = await jget('/api/missions/'+d.id+'/file?path='+encodeURIComponent(sel.path));
    if(j.kind==='image') box.innerHTML = `<img src="/api/missions/${d.id}/file?path=${encodeURIComponent(sel.path)}&raw=1" style="max-width:100%;max-height:44vh;border:1px solid var(--border-dim);border-radius:8px">`;
    else if(j.kind==='binary') box.innerHTML = '<i>binary file — '+j.size+' bytes</i>';
    else if(/\.(md|txt)$/i.test(sel.path)) box.innerHTML = mdLite(j.text)+(j.truncated?'<i>… truncated</i>':'');
    else if(/\.html?$/i.test(sel.path)) box.innerHTML = `<iframe sandbox="" srcdoc="${esc(j.text)}" style="width:100%;height:340px;border:1px solid var(--border-dim);border-radius:8px;background:#fff"></iframe><details style="margin-top:8px"><summary>source</summary><pre>${esc(j.text)}</pre></details>`;
    else box.innerHTML = '<pre>'+esc(j.text)+'</pre>';
  }catch(e){ box.textContent = 'could not load this file: '+e.message; }
}
window.mTranscript = async (id) => {
  $('tr-scrim').classList.add('open'); $('tr-modal').classList.add('open');
  const body = $('tr-body'); body.textContent = 'loading…';
  try{
    const r = await jget('/api/missions/'+id+'/rows?node=all&full=1');
    body.innerHTML = r.rows.length ? r.rows.map(fullRow).join('') : '<span style="color:var(--text-faint)">no transcript yet</span>';
    const m = MISSIONS.find(x=>x.id===id);
    $('tr-oc').style.display = (m && m.session_id && m.runtime==='opencode') ? '' : 'none';
    $('tr-oc').onclick = () => openOC(id);
  }catch(e){ body.textContent = 'transcript unavailable: '+e.message; }
};
function fullRow(e){ const k = e.k||'step';
  if(k==='step') return `<div class="trh">${esc(e.text)}</div>`;
  if(k==='prompt') return `<details class="pmt" open><summary>${ic('inbox')}PROMPT — what this agent was asked (${(e.text||'').length} chars)</summary><pre>${esc(e.text)}</pre></details>`
      + (e.system ? `<details class="pmt"><summary>SYSTEM — persona and rules</summary><pre>${esc(e.system)}</pre></details>` : '');
  if(k==='text') return `<div class="rep">REPLY</div><div class="trt">${esc(e.text)}</div>`;
  return feedRow(e); }
window.openOC = async (id, sid) => { try{ const r = await jpost('/api/missions/'+id+'/transcript', sid ? {session_id:sid} : {}); window.open(r.root_url, 'oc-'+id); }catch(e){ toast('could not open OpenCode: '+e.message,'err'); } };
function closeTr(){ $('tr-scrim').classList.remove('open'); $('tr-modal').classList.remove('open'); }
function fmtS(s){ return s>=60 ? Math.floor(s/60)+'m'+String(Math.round(s%60)).padStart(2,'0')+'s' : Math.round(s)+'s'; }
function ownerSecs(d){        // seconds per node: orch, each step id, gate (fixes / revisions)
  const out = {}; let owner = '';
  for(const g of ((d.runmap||{}).segments||[])){
    const ph = g.phase||''; let who; const mo = ph.match(/^step (\S+) /);
    if(mo){ owner = mo[1]; who = owner; }
    else if(/^(fix |revise|re-review)/.test(ph)) who = 'gate';
    else if(ph.startsWith('nudge')) who = owner;
    else who = (g.agent==='orchestrator') ? 'orch' : owner;
    out[who] = (out[who]||0) + (g.secs||0);
  }
  return out;
}
function totalSecs(d){ return Object.values(ownerSecs(d)).reduce((a,b)=>a+b,0); }
function timeBar(d){
  const os = ownerSecs(d); const g = pipeGraph(d);
  const items = g.nodes.filter(n=>n.id!=='req' && (os[n.id] || nodeState(d,n)==='running')).sort((a,b)=>a.depth-b.depth);
  if(!items.length) return '';
  const tot = items.reduce((a,n)=>a+(os[n.id]||0),0) || 1;
  const n = (d.plan||[]).length, done = (d.plan||[]).filter(s=>s.status==='done').length;
  const lab = (x) => x.id==='orch' ? 'orchestrator' : x.id==='gate' ? 'hub checks' : (x.step ? x.step.agent : x.name.toLowerCase());
  const segs = items.map(x=>{ const secs = os[x.id]||0, st = nodeState(d,x);
    return `<span class="ts ${st}" style="flex:${Math.max(secs, tot*0.05)}" title="${esc(lab(x))} · ${fmtS(secs)}">${secs/tot>0.13?esc(lab(x)):''}</span>`; }).join('');
  const leg = items.map(x=>`<b>${esc(lab(x))}</b> ${fmtS(os[x.id]||0)}`).join(' · ');
  return `<div class="tbox"><div class="trk"><span>${n?`STEP ${Math.min(done+(d.status==='running'?1:0),n)} OF ${n}`:'PLANNING'}</span><span>TOTAL ${fmtS(tot)}</span></div>
    <div class="timeline-bar">${segs}</div><div class="tleg">${leg}</div></div>`;
}
const PSEL = {}, ASKSEL = {};
const PW = 134, PH = 90, GX = 42, GY = 16;
const RO = ['reviewer','editor','compliance-reviewer'];
function topoSteps(steps){
  const ids = new Set(steps.map(s=>s.id)), out = [], left = [...steps];
  while(left.length){
    const placed = new Set(out.map(x=>x.id));
    const nx = left.find(x=>(x.depends_on||[]).every(dd=>placed.has(dd)||!ids.has(dd))) || left[0];
    out.push(nx); left.splice(left.indexOf(nx),1);
  }
  return out;
}
function synthSteps(d){                                     // single / team missions have no plan: draw their agents as a pipeline too
  const fin = ['awaiting_review','applied'].includes(d.status), bad = ['failed','timed_out'].includes(d.status);
  if(d.kind==='team' && (d.agents||[]).length){
    const cur = d.agents.indexOf(d.agent);
    return d.agents.map((a,i)=>({id:'t'+(i+1), agent:a, brief:d.brief, depends_on:i?['t'+i]:[], summary:'',
      status: fin ? 'done' : d.status==='running' ? (i<cur?'done':i===cur?'running':'queued') : bad ? (i<cur?'done':i===cur?'failed':'proposed') : 'proposed'}));
  }
  if(d.kind==='single' || d.kind==='parallel'){
    return [{id:'s1', agent:d.agent||'agent', brief:d.brief, depends_on:[], summary:'',
      status: fin ? 'done' : d.status==='running' ? 'running' : bad ? 'failed' : 'proposed'}];
  }
  return [];
}
const shortM = (x) => String(x||'').replace(/^(opencode|ollama)\//,'');
const SRC = {pinned:'pinned on this step', suggested:'★ suggested', 'agent setting':"the agent's own setting", mission:'mission default'};
function stepModel(d, st){                        // same order the hub uses: step pin > agent setting > mission model
  if(st.eff_model) return [st.eff_model, st.eff_src || ''];
  if(st.model) return [st.model, st.model_src === 'suggested' ? 'suggested' : 'pinned'];
  const o = (((AGENTS.find(a=>a.name===st.agent)||{}).settings||{}).model)||{};
  if(o.source === 'override' && o.value) return [o.value, 'agent setting'];
  return [d.model || '', 'mission'];
}
function pipeGraph(d){
  const steps = (d.plan && d.plan.length) ? d.plan : synthSteps(d);
  const hasOrch = d.kind==='orchestrator';
  const nodes = hasOrch ? [{id:'orch',name:'ORCHESTRATOR',kind:'agent',deps:[]}] : [];      // the ask itself is the page title
  if(steps.length){
    const order = topoSteps(steps);
    const firstRO = order.findIndex(x=>RO.includes(x.agent));
    const before = firstRO<0 ? order : order.slice(0, firstRO);            // what the hub checks BEFORE the first reviewer
    const beforeIds = new Set(before.map(x=>x.id));
    const leaves = before.filter(x=>!before.some(y=>(y.depends_on||[]).includes(x.id))).map(x=>x.id);
    order.forEach(x=>{
      const own = x.depends_on||[];
      let deps;
      if(RO.includes(x.agent)){ const keep = own.filter(i=>!beforeIds.has(i)); deps = (!own.length || own.some(i=>beforeIds.has(i))) ? ['gate', ...keep] : keep; }
      else deps = own.length ? own : (hasOrch ? ['orch'] : []);
      nodes.push({id:x.id, name:x.agent.toUpperCase(), kind:'step', step:x, deps});
    });
    nodes.push({id:'gate', name:'HUB CHECKS', kind:'hub', deps: leaves.length ? leaves : (hasOrch ? ['orch'] : [])});
  }
  const byId = Object.fromEntries(nodes.map(n=>[n.id,n]));
  const dp = (n, seen) => { if(n.depth!=null) return n.depth; if(seen.has(n.id)) return 0; seen.add(n.id);
    n.depth = n.deps.length ? 1+Math.max(...n.deps.map(x=>byId[x]?dp(byId[x],seen):0)) : 0; return n.depth; };
  nodes.forEach(n=>dp(n,new Set()));
  if(!nodes.length) return {nodes:[], byId:{}, edges:[], cols:[], TOP:0, w:0, h:0};
  const nc = Math.max(...nodes.map(n=>n.depth))+1, cols = Array.from({length:nc},()=>[]);
  nodes.forEach(n=>cols[n.depth].push(n));
  cols.forEach((col,ci)=>{                                                   // order rows by the average row of the parents
    col.forEach((n,i)=>{ const ps = n.deps.map(x=>byId[x]).filter(x=>x&&x.row!=null); n.key = ps.length ? ps.reduce((a,b)=>a+b.row,0)/ps.length : i; });
    col.sort((a,b)=>a.key-b.key); col.forEach((n,i)=>{ n.row = i; });
  });
  const maxRows = Math.max(...cols.map(c=>c.length));
  // long edges that would run straight through a box detour over the top lane
  const edges = []; nodes.forEach(n=>n.deps.forEach(dep=>{ const a = byId[dep]; if(a) edges.push({a,n}); }));
  const blocked = (e) => nodes.some(k=>k.depth>e.a.depth && k.depth<e.n.depth && Math.abs((k.row - e.a.row)) < 0.5);
  edges.forEach(e=>{ e.lane = (e.n.depth-e.a.depth>1 && blocked(e)); });
  const lanes = edges.filter(e=>e.lane).length, TOP = 12 + lanes*7;
  nodes.forEach(n=>{ n.nOut = edges.filter(e=>e.a===n).length; n.nIn = edges.filter(e=>e.n===n).length; });
  const gut = {}; edges.forEach(e=>{ const k = e.n.depth; gut[k] = gut[k]||[]; e.ch = gut[k].length; gut[k].push(e); });
  edges.forEach(e=>{ e.chN = gut[e.n.depth].length; });
  nodes.forEach(n=>{ const col = cols[n.depth]; n.x = n.depth*(PW+GX); n.y = TOP + ((maxRows-col.length)/2 + n.row)*(PH+GY); });
  return {nodes, byId, edges, cols, TOP, w: nc*(PW+GX)-GX+4, h: TOP + maxRows*(PH+GY) + 4};
}
function rpath(pts, r){
  r = r||9; let d = `M${pts[0][0]} ${pts[0][1]}`;
  for(let i=1;i<pts.length-1;i++){
    const [x0,y0]=pts[i-1],[x1,y1]=pts[i],[x2,y2]=pts[i+1];
    const l1=Math.hypot(x1-x0,y1-y0)||1, l2=Math.hypot(x2-x1,y2-y1)||1, rr=Math.min(r,l1/2,l2/2);
    d += ` L${x1-(x1-x0)/l1*rr} ${y1-(y1-y0)/l1*rr} Q${x1} ${y1} ${x1+(x2-x1)/l2*rr} ${y1+(y2-y1)/l2*rr}`;
  }
  const L = pts[pts.length-1]; return d+` L${L[0]} ${L[1]}`;
}
function edgePts(g, e, k){                        // polyline of one edge (also used by the layout self-check)
  const a=e.a, n=e.n, x1=a.x+PW, x2=n.x;
  const y1=a.y+PH/2+(a.nOut>1?-4:0), y2=n.y+PH/2+(n.nIn>1?4:0);      // outgoing ports sit above centre, incoming below: no shared line
  const xm = (x2-GX+3) + (GX-6)*((e.ch+0.5)/(e.chN||1));            // every edge gets its own vertical channel in the gutter
  if(e.lane){
    const ly = g.TOP - 6 - k*7, xa = x1+6+((a.row%5))*5;
    return [[x1,y1],[xa,y1],[xa,ly],[xm,ly],[xm,y2],[x2,y2]];
  }
  return Math.abs(y1-y2)<1 ? [[x1,y1],[x2,y2]] : [[x1,y1],[xm,y1],[xm,y2],[x2,y2]];
}
function edgePath(g, e, k){ const pts = edgePts(g, e, k); return pts.length===2 ? `M${pts[0][0]} ${pts[0][1]} L${pts[1][0]} ${pts[1][1]}` : rpath(pts); }
function fitPipe(){
  const cv = $('cv'), w = $('pwrap'), c = $('pcanvas'); if(!cv||!w||!c) return;
  const W = parseFloat(c.style.width), H = parseFloat(c.style.height);
  const k = Math.max(0.78, Math.min(1, (cv.clientWidth-26)/W));
  c.style.transform = `scale(${k})`; c.style.transformOrigin = '0 0';
  w.style.width = (W*k)+'px'; w.style.height = (H*k)+'px';
}
function segFor(d, sid){ return ((d.runmap||{}).segments||[]).find(x=>(x.phase||'').indexOf('step '+sid+' ')===0); }
function nodeState(d, n){
  const st = d.status;
  if(n.id==='req') return 'done';
  if(n.id==='orch') return st==='needs_input' ? 'wait' : (st==='running' && !(d.plan||[]).length ? 'running' : 'done');
  if(n.kind==='hub'){
    if(d.verify) return d.verify.ok ? 'done' : 'fail';
    const deps = n.deps.map(x=>(d.plan||[]).find(s=>s.id===x)).filter(Boolean);
    return (st==='running' && deps.length && deps.every(s=>s.status==='done')) ? 'running' : 'proposed';
  }
  const s = n.step.status;
  if(st!=='running' && s==='running') return 'fail';            // interrupted run: nothing is actually working
  return s==='done' ? 'done' : s==='running' ? 'running' : s==='failed' ? 'fail' : 'proposed';
}
function pipelineBlock(d){
  const askOpen = d.status==='needs_input';
  const g = pipeGraph(d);
  if(!g.nodes.length) return '';
  const sel = PSEL[d.id] || (askOpen ? 'orch' : ((d.plan||[]).find(s=>s.status==='running')||{}).id || (g.byId.orch ? 'orch' : g.nodes[0].id));
  let ed = '', lane = 0;
  g.edges.forEach(e=>{
    const sa = nodeState(d,e.a), sb = nodeState(d,e.n);
    const col = sb==='proposed' ? '#b07cd6' : (sa==='done' ? 'rgba(0,230,118,.8)' : 'rgba(0,230,118,.28)');
    const dash = (sb==='proposed'||(sa==='done'&&sb==='running')) ? ' stroke-dasharray="6 5"' : '';
    ed += `<path d="${edgePath(g, e, e.lane ? lane++ : 0)}" fill="none" stroke="${col}" stroke-width="1.7"${dash} marker-end="url(#${sb==='proposed'?'pap':'pa'})"/>`;
  });
  const nd = g.nodes.map(n=>{
    const s = nodeState(d,n); const sg = n.step ? segFor(d,n.id) : null;
    let tg = '', i = '', o = '', tm = '', act = '';
    if(n.id==='req'){ tg='you'; o=(d.brief||'').slice(0,50); }
    else if(n.id==='orch'){ tg=(d.status==='needs_input'?'asking you':(d.plan||[]).length?((d.plan||[]).length+' steps planned'):'planning'); i='request'+((d.answers||[]).length?' + answers':''); o=(d.plan||[]).length?'plan':''; if(s==='wait') act='? waiting for you'; const t=ownerSecs(d).orch; if(t) tm=fmtS(t); }
    else if(n.kind==='hub'){ tg='compile + tests · no LLM'; if(d.verify){ o=(d.verify.ok?'passed':'FAILED')+(d.verify.attempts?' ('+d.verify.attempts+' fix)':''); } const t=ownerSecs(d).gate; if(t) tm=fmtS(t); }
    else { tg=n.step.id+(n.step.depends_on.length?' · after '+n.step.depends_on.join(','):''); i=(n.step.brief||'').slice(0,54);
      o = n.step.verdict ? ((n.step.rounds?'revised ×'+n.step.rounds+' → ':'')+n.step.verdict) : n.step.status==='done' ? (((sg&&sg.files)||[]).length ? 'wrote '+sg.files.join(', ') : 'done') : n.step.status==='failed' ? (n.step.note||'failed') : '';
      const t=ownerSecs(d)[n.id]; if(t) tm=fmtS(t); if(s==='running') act='▸ working…'; if(s==='proposed') act='planned · not dispatched'; }
    const sm = n.step ? stepModel(d, n.step) : null;
    return `<button class="pn ${s}${n.kind==='hub'?' hub':''}${sel===n.id?' sel':''}" data-n="${n.id}" style="left:${n.x}px;top:${n.y}px"${sm&&sm[0]?` title="runs on ${esc(shortM(sm[0]))} · ${esc(SRC[sm[1]]||sm[1])}"`:''}>
      <div class="hd"><span class="dot ${s==='proposed'?'plan_ready':s==='fail'?'failed':s==='wait'?'needs_input':s==='done'?'awaiting_review':s}"></span>${n.name}<span class="tm">${tm}</span></div>
      <div class="tg">${esc(tg)}</div>${i?`<span class="io"><em>IN</em>${esc(i)}</span>`:''}${o?`<span class="io o"><em>OUT</em>${esc(o)}</span>`:''}${act?`<div class="st">${esc(act)}</div>`:''}</button>`;
  }).join('');
  return `<h2>${(d.plan||[]).length?'Pipeline — who does what, in order':'Pipeline — appears once the orchestrator has planned'}</h2>
    ${askOpen ? askBlock(d) : ''}
    <div class="cv" id="cv"><div class="pwrap" id="pwrap"><div class="pcanvas" id="pcanvas" style="width:${g.w}px;height:${g.h}px"><svg><defs><marker id="pa" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L8 4L0 8z" fill="rgba(0,230,118,.8)"/></marker><marker id="pap" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L8 4L0 8z" fill="#b07cd6"/></marker></defs>${ed}</svg>${nd}</div></div>
      <div class="pleg"><span>solid box = LLM agent</span><span>dashed box = hub-run (no LLM)</span><span style="color:var(--purple)">purple = planned, not dispatched</span><span>click a box for its brief, result, model, transcript</span></div></div>
    ${d.status==='plan_ready' ? `<div class="row" style="margin-top:10px"><button class="btn" id="m-addstep">${ic('plus')}ADD STEP</button><span style="font-size:11px;color:var(--text-muted)">edit any step below; nothing runs until you press RUN PIPELINE above</span></div>` : ''}
    <div class="pdraw" id="pdraw">${pipeDrawer(d,g,sel)}</div>`;
}
function pipeDrawer(d,g,sel){
  const n = g.byId[sel] || g.byId.orch || g.nodes[0]; const s = nodeState(d,n);
  const lab = {done:'DONE',running:'WORKING',wait:'YOUR TURN',proposed:'PLANNED',fail:'FAILED'}[s];
  let kv='', body='';
  if(n.id==='req') body = `<div class="lb">BRIEF</div><pre>${esc(d.brief)}</pre>`;
  else if(n.id==='orch'){
    kv = `<span>model</span><span>${esc(d.model||'—')}</span>`;
    if((d.answers||[]).length) body += `<div class="lb">YOUR ANSWERS</div><pre>${esc(d.answers.map(a=>a.q+' → '+a.a).join('\n'))}</pre>`;
    body += `<div class="lb">PLAN</div><pre>${esc((d.plan||[]).map(p=>p.id+'  '+p.agent+(p.depends_on.length?'  (after '+p.depends_on.join(',')+')':'')+'\n    '+p.brief).join('\n')||'— not planned yet —')}</pre>`;
  } else if(n.kind==='hub'){
    const v = d.verify;
    kv = `<span>type</span><span>hub-run check, no LLM</span>`;
    body = v ? `<div class="lb">RESULT — ${esc(v.step||'')}${v.attempts?` · ${v.attempts} auto-fix round(s)`:''}</div><pre>${esc(v.output||'')}</pre>` : '<div class="lb">Runs before the reviewer: compile every changed .py, then pytest if tests exist. A failure goes back to the coder.</div>';
  } else {
    const sg = segFor(d,n.id), st = n.step;
    const sm = stepModel(d, st);
    kv = `<span>model</span><span>${esc(shortM((sg&&sg.model)||sm[0])||'—')} <small style="color:var(--text-muted)">· ${esc(SRC[sm[1]]||sm[1])}</small></span><span>time</span><span>${sg?fmtS(sg.secs||0):'—'}</span>`
       + (sg ? `<span>steps</span><span>${sg.steps}${sg.prompt?` · prompt ${Math.round(sg.prompt/100)/10}k`:''}${sg.tok_out?` · out ${sg.tok_out}`:''}</span>` : '')
       + ((sg&&sg.files||[]).length ? `<span>wrote</span><span>${esc(sg.files.join(', '))}</span>` : '')
       + (recPick(st.agent) ? `<span>suggested</span><span>${esc(recPick(st.agent))}${st.model?` · pinned: ${esc(st.model)}`:''}</span>` : '');
    body = d.status==='plan_ready' ? stepEditor(d, st) :
           `<div class="lb">ITS BRIEF (from the orchestrator)</div><pre>${esc(st.brief)}</pre>`
         + (st.summary ? `<div class="lb">WHAT IT REPORTED</div><pre>${esc(st.summary)}</pre>` : '');
  }
  return `<b style="font-size:13px">${esc(n.name)}</b> <span class="pill">${lab}</span><div class="kv">${kv}</div>${body}
    ${n.id==='req' ? '' : `<div class="lb">THIS AGENT'S TRANSCRIPT — the prompt it was given, then what it answered and did</div><div class="feed" id="nrows" style="max-height:440px">loading…</div>`}
    <div class="row" style="margin-top:8px">${(n.step && ['awaiting_review','paused','failed','timed_out'].includes(d.status) && ['done','failed'].includes(n.step.status)) ? `<button class="btn" data-resume="${esc(n.id)}">RE-RUN FROM THIS STEP</button>` : ''}<button class="btn" onclick="mTranscript('${d.id}')">FULL TRANSCRIPT (all agents)</button>${ocBtn(d,n)}</div>${ocNote(d,n)}`;
}
function nodeSeg(d, n){ return n.id==='orch' ? ((d.runmap||{}).segments||[]).find(x=>x.agent==='orchestrator') : (n.step ? segFor(d,n.id) : null); }
function ocBtn(d, n){ const sg = nodeSeg(d,n); return (sg && sg.session && d.runtime==='opencode') ? `<button class="btn" data-oc="${esc(sg.session)}">OPEN THIS AGENT'S OPENCODE CHAT</button>` : ''; }
function ocNote(d, n){ const sg = nodeSeg(d,n); return (sg && !sg.session && d.runtime==='opencode') ? `<div class="note" style="color:var(--text-muted)">This agent was answered by ONE direct model call, so there is no OpenCode chat window for it — the exact prompt and reply are in the transcript above.</div>` : ''; }
function allowedAgents(d){
  const pool = (d.agents && d.agents.length) ? d.agents : ((PROFILES[d.profile]||{}).roster || []);
  return pool.length ? pool : ['coder'];
}
function stepEditor(d, st){
  const ag = allowedAgents(d);
  const others = (d.plan||[]).filter(x=>x.id!==st.id);
  return `<div class="lb">EDIT THIS STEP (saved into the plan; nothing has run yet)</div>
    <div class="kv"><span>agent</span><span><select id="pe-agent">${ag.map(a=>`<option ${a===st.agent?'selected':''}>${esc(a)}</option>`).join('')}</select></span>
      <span>model</span><span><select id="pe-model"><option value="">— mission default —</option>${MODELS.map(m=>`<option value="${esc(m.id)}" ${m.id===st.model?'selected':''}>${esc(m.id)}${m.local?' · local':(m.free?' · free':'')}</option>`).join('')}</select></span>
      <span>after</span><span>${others.length?others.map(o=>`<label class="ck" style="display:inline-flex;margin-right:10px"><input type="checkbox" class="pe-dep" value="${esc(o.id)}" ${(st.depends_on||[]).includes(o.id)?'checked':''}> ${esc(o.id)} · ${esc(o.agent)}</label>`).join(''):'<i>nothing else in the plan</i>'}</span></div>
    <div class="note" style="margin:6px 0">${recLine(st.agent)||'<span style="color:var(--text-faint)">no suggestion for this agent yet</span>'}${recPick(st.agent)?` <button class="btn" id="pe-usesug" style="min-height:24px;padding:3px 8px">USE</button>`:''}</div>
    <textarea id="pe-brief" style="min-height:96px">${esc(st.brief)}</textarea>
    <div class="row" style="margin-top:8px"><button class="btn go" id="pe-save">SAVE STEP</button><button class="btn stop" id="pe-del">DELETE STEP</button></div>`;
}
function editedPlan(d, id, mut){
  let steps = (d.plan||[]).map(x=>({id:x.id, agent:x.agent, brief:x.brief, depends_on:x.depends_on||[], model:x.model||''}));
  steps = mut(steps) || steps;
  return steps;
}
async function savePlan(d, steps, selectId){
  try{ await jpost('/api/missions/'+d.id+'/plan',{steps}); if(selectId) PSEL[d.id]=selectId; }
  catch(e){ toast(e.message,'err'); return; }
  $('pane').dataset.sig=''; $('pane').dataset.full=''; renderDetail(d.id);
}
async function loadNodeRows(d){
  const box = $('nrows'); if(!box) return;
  const node = PSEL[d.id] || 'orch';
  try{
    const r = await jget('/api/missions/'+d.id+'/rows?full=1&node='+encodeURIComponent(node));
    const pinned = box.scrollTop + box.clientHeight >= box.scrollHeight - 30;
    box.innerHTML = r.rows.length ? r.rows.map(fullRow).join('') : '<span style="color:var(--text-faint)">nothing yet — this agent has not started</span>';
    if(pinned) box.scrollTop = box.scrollHeight;
  }catch(e){ box.textContent = 'transcript unavailable'; }
}
function askBlock(d){
  const sel = ASKSEL[d.id] = ASKSEL[d.id] || {};
  return `<div class="ask" id="askcard"><h3>ORCHESTRATOR NEEDS YOUR INPUT · ${d.questions.length} QUESTION${d.questions.length>1?'S':''}</h3>
    ${d.questions.map((q,i)=>`<div class="q"><b>${esc(q.q)}</b>${q.why?`<i>${esc(q.why)}</i>`:''}
      <div class="chips" data-qi="${i}">${(q.options||[]).map(o=>`<button type="button" class="pick ${o===q.default?'rec':''} ${((sel[i]!=null?sel[i]:q.default)===o)?'sel':''}" data-v="${esc(o)}">${esc(o)}</button>`).join('')}</div>
      <input type="text" data-qi="${i}" placeholder="or type your own answer" value="${esc((q.options||[]).includes(sel[i])||sel[i]==null?'':sel[i])}"></div>`).join('')}
    <div class="row"><button class="btn go" id="m-answer">ANSWER &amp; CONTINUE</button><button class="btn" id="m-answer-def">USE ★ DEFAULTS</button></div></div>`;
}
function bindPipeline(d){
  document.querySelectorAll('#pane .pn').forEach(b=>b.onclick=()=>{ PSEL[d.id]=b.dataset.n; $('pane').dataset.sig=''; $('pane').dataset.full=''; renderDetail(d.id); });
  const sv = $('pe-save'); if(sv){ const sid = PSEL[d.id];
    sv.onclick = () => savePlan(d, editedPlan(d, sid, st=>{ const x=st.find(y=>y.id===sid); if(!x) return;
      x.agent=$('pe-agent').value; x.model=$('pe-model').value; x.brief=$('pe-brief').value.trim();
      x.depends_on=[...document.querySelectorAll('.pe-dep:checked')].map(c=>c.value); }), sid);
    $('pe-del').onclick = () => { if(!confirm('Delete this step from the plan?')) return;
      savePlan(d, editedPlan(d, sid, st=>st.filter(y=>y.id!==sid)), 'orch'); }; }
  const us = $('pe-usesug'); if(us) us.onclick = () => { const sel=$('pe-model'); const v=recPick($('pe-agent').value);
    if(![...sel.options].some(o=>o.value===v)){ const o=document.createElement('option'); o.value=v; o.textContent=v+' (suggested)'; sel.appendChild(o); } sel.value=v; };
  const ad = $('m-addstep'); if(ad) ad.onclick = () => { const n=(d.plan||[]).length+1; let id='s'+n; while((d.plan||[]).some(x=>x.id===id)) id+='x';
    savePlan(d, editedPlan(d, null, st=>[...st,{id, agent:allowedAgents(d)[0], brief:'Describe exactly what this step must produce, which files, and what done looks like.', depends_on:[], model:''}]), id); };
  const rp = $('m-runplan'); if(rp) rp.onclick = async () => { try{ await jpost('/api/missions/'+d.id+'/run-plan',{use_suggested: !!($('m-usesug')&&$('m-usesug').checked)}); }catch(e){ toast(e.message,'err'); } refresh(); select(d.id); };
  const ac = $('askcard'); if(!ac) return;
  const sel = ASKSEL[d.id] = ASKSEL[d.id] || {};
  ac.querySelectorAll('.pick').forEach(p=>p.onclick=()=>{ const qi=p.parentNode.dataset.qi; sel[qi]=p.dataset.v;
    p.parentNode.querySelectorAll('.pick').forEach(x=>x.classList.toggle('sel',x===p)); ac.querySelector('input[data-qi="'+qi+'"]').value=''; });
  ac.querySelectorAll('input[type=text]').forEach(inp=>inp.oninput=()=>{ const qi=inp.dataset.qi;
    if(inp.value.trim()){ sel[qi]=inp.value.trim(); ac.querySelectorAll('.chips[data-qi="'+qi+'"] .pick').forEach(x=>x.classList.remove('sel')); } });
  const send = async (defaults) => {
    const answers = d.questions.map((q,i)=>({q:q.q, a: defaults ? q.default : (sel[i]!=null ? sel[i] : q.default)}));
    try{ await jpost('/api/missions/'+d.id+'/answer',{answers}); delete ASKSEL[d.id]; }catch(e){ toast(e.message,'err'); return; }
    refresh(); select(d.id);
  };
  $('m-answer').onclick = () => send(false); $('m-answer-def').onclick = () => send(true);
}
function checksBlock(d){
  const v = d.verify; if(!v) return '';
  return `<h2>Hub checks</h2><div class="chk ${v.ok?'ok':'bad'}"><b>${v.ok?'✓ passed':'✗ failed'}</b> · ${esc(v.step||'')}${v.attempts?` · fixed after ${v.attempts} auto-fix round${v.attempts>1?'s':''}`:''}<pre>${esc(v.output||'')}</pre></div>`;
}
let RECS = {};
async function loadRecs(){ try{ RECS = await jget('/api/model-recommendations'); }catch(e){} }
function recPick(role){ const r=(RECS.roles||{})[role]; return r ? r.pick : ''; }
function recLine(role){ const r=(RECS.roles||{})[role]; if(!r) return '';
  return `<span style="color:var(--amber)">★ suggested for ${esc(role)}:</span> <b>${esc(r.pick)}</b> <span style="color:var(--text-muted)">— ${esc(r.why)}</span>${RECS.basis&&/^hypothesis/.test(RECS.basis)?' <i>(untested guess)</i>':''}`; }
function recFor(role){ const r=(RECS.roles||{})[role];
  return r ? `Suggested for <b>${esc(role)}</b>: <b>${esc(r.pick)}</b> — ${esc(r.why)}${RECS.basis&&/^hypothesis/.test(RECS.basis)?' <i>(untested guess)</i>':''}` : ''; }
function planBlock(d){
  const props = d.children.filter(c=>c.status==='proposed');
  return `<h2>Plan · ${d.children.length} sub-mission${d.children.length===1?'':'s'}</h2>
    <div>${d.children.map(c=>`<div class="card" style="cursor:default"><div class="top"><span class="dot ${c.status}"></span>
      <span class="ag">${esc(c.agent)}</span><span class="pill">${esc(c.project_name)}</span>${(c.depends_on||[]).length?`<span class="pill">after ${esc(c.depends_on.map(x=>x.split(':')[1]).join(', '))}</span>`:''}<span class="spacer"></span><span style="font-size:10px">${esc(c.status)}</span></div>
      <div class="br">${esc(c.brief)}</div>
      ${c.status==='proposed'?`<button class="btn" style="margin-top:6px" onclick="jpost('/api/missions/${c.id}/dispatch',{}).then(refresh)">DISPATCH</button>`:''}</div>`).join('')}</div>
    ${props.length?`<button class="btn go" style="margin-top:8px" onclick="jpost('/api/missions/plan/${d.parent_id||d.id}/dispatch-all',{}).then(refresh)">DISPATCH ALL (${props.length})</button>`:''}`;
}
function feedRow(e){ const k=e.k||'step'; const icon={tool:ic('tool'),text:ic('chat'),err:ic('x'),step:'▸',reasoning:'…'}[k]||'·';
  return `<div class="${k==='err'?'err':k}">${icon} ${esc(e.text)}</div>`; }
function renderFiles(d){
  const ul=$('mfiles'); if(!ul)return;
  ul.innerHTML = (d.changed_files||[]).length
    ? '' : '<li style="color:var(--text-faint);cursor:default">no changes'+(d.status==='running'?' yet':'')+'</li>';
  (d.changed_files||[]).forEach(f=>{ const li=document.createElement('li');
    li.innerHTML=`<span class="badge">${esc(f.status)}</span>${esc(f.path)}`;
    li.onclick=()=>showDiff(d.id,f.path); ul.appendChild(li); });
}
async function showDiff(id,path){
  const pre=$('mdiff'); pre.style.display='block'; pre.textContent='loading…';
  const t=await (await fetch('/api/missions/'+id+'/diff?path='+encodeURIComponent(path))).text();
  pre.innerHTML=''; t.split('\n').forEach(l=>{ const s=document.createElement('div');
    if(l.startsWith('+')&&!l.startsWith('+++'))s.className='diff-add';
    else if(l.startsWith('-')&&!l.startsWith('---'))s.className='diff-del';
    s.textContent=l; pre.appendChild(s); });
}
window.jpost = jpost; window.refresh = refresh;

// ── new mission ──────────────────────────────────────────────────────────
function newMission(preProject){
  SEL=null; showDetail(true); renderList(); $('hollow').style.display='none'; $('pane').style.display='flex';
  if(window.HubVoice) HubVoice.contextChanged('new-ask');
  const workers = AGENTS.filter(a=>a.name!=='orchestrator' && !a.utility);
  const single1 = (workers.find(a=>a.name==='coder')||workers[0]||{}).name || 'coder';
  let TEAM = [single1];                          // ordered relay for team mode
  let PMODE = 'existing';                        // existing | new

  const projSingle = PROJECTS.map(p=>`<option value="${esc(p.slug)}" ${p.slug===preProject||p.name===preProject?'selected':''}>${esc(p.name)}</option>`).join('')
                   || '<option value="">— no projects —</option>';
  const projChecks = PROJECTS.map(p=>`<label class="ck"><input type="checkbox" class="nm-pcheck" value="${esc(p.slug)}" ${p.slug===preProject||p.name===preProject?'checked':''}> ${esc(p.name)}</label>`).join('')
                   || '<span style="color:var(--text-faint)">no projects</span>';
  const agentSel = workers.map(a=>`<option value="${esc(a.name)}" ${a.name===single1?'selected':''}>${esc(a.name)}</option>`).join('');
  const agentChecks = (pref)=>workers.map(a=>`<label class="ck"><input type="checkbox" class="${pref}" value="${esc(a.name)}" ${['coder','reviewer'].includes(a.name)?'checked':''}> ${esc(a.name)}</label>`).join('');
  const wModel = (MODELS.find(m=>m.workspace_default)||{}).id || '';
  const modelOpts = `<option value="">— workspace default${wModel?' ('+esc(wModel)+')':''} —</option>` +
     MODELS.map(m=>`<option value="${esc(m.id)}">${esc(m.id)}${m.local?' · local':(m.free?' · free':'')}</option>`).join('');

  $('pane').innerHTML = `<div class="dhead"><h1>New mission</h1></div>
    <div class="dscroll">
      <label>Project</label>
      <div class="row" style="gap:6px">
        <button type="button" class="btn nm-pm sel" data-pm="existing">EXISTING</button>
        <button type="button" class="btn nm-pm" data-pm="new">${ic('plus')}NEW PROJECT</button>
      </div>
      <div id="nm-pex" style="margin-top:8px">
        <select id="nm-proj">${projSingle}</select>
        <div id="nm-pmulti" style="display:none" class="cklist">${projChecks}</div>
        <div id="nm-phint" class="note" style="color:var(--text-faint)"></div>
      </div>
      <div id="nm-pnew" style="display:none;margin-top:8px">
        <input type="text" id="nm-newname" placeholder="my-idea — new git repo under _unsorted projects/">
      </div>
      <div class="note" style="color:var(--text-muted);margin-top:8px">The agent works on a private copy. You review the result as a diff and choose APPLY or DISCARD — nothing touches the repo until you APPLY.</div>

      <label>Work type</label>
      <select id="nm-profile">${Object.entries(PROFILES).map(([k,v])=>`<option value="${esc(k)}">${esc(v.label)}</option>`).join('')||'<option value="code">Software</option>'}</select>
      <div class="note" id="nm-prof-hint" style="color:var(--text-muted)"></div>
      <label class="ck" style="margin-top:8px"><input type="checkbox" id="nm-ref"> Use the LLM Wiki as a reference library (copied into the working copy; agents cite it as [[page]])</label>

      <label>Brief</label>
      <textarea id="nm-brief" placeholder="Exactly what to do. e.g. Add a --dry-run flag to cli.py that prints planned actions without executing; update the README usage block."></textarea>

      <label>Run as</label>
      <div class="row" style="gap:12px;flex-wrap:wrap">
        ${[['orchestrator','Orchestrated (recommended)'],['single','Direct — one agent'],['team','Team relay'],['parallel','Parallel drafts']].map(([v,t],i)=>
          `<label style="display:flex;gap:6px;align-items:center;margin:0;color:var(--text)"><input type="radio" name="nm-kind" value="${v}" ${i===0?'checked':''} style="width:auto"> ${t}</label>`).join('')}
      </div>
      <div class="note" style="color:var(--text-muted)">Orchestrated: an orchestrator asks you what it needs, plans, then a pipeline of agents runs in one working copy — you approve the plan, review the result, APPLY.</div>

      <div id="nm-m-single" style="display:none"><label>Agent</label><select id="nm-agent">${agentSel}</select></div>

      <div id="nm-m-team" style="display:none">
        <label>Agents in order — each builds on the last, one combined diff</label>
        <div id="nm-teamlist"></div>
        <div class="row" style="margin-top:6px"><select id="nm-teamadd">${agentSel}</select>
          <button type="button" class="btn" id="nm-teamplus">${ic('plus')}ADD</button></div>
      </div>

      <div id="nm-m-parallel" style="display:none">
        <label>Agents — each runs the same brief on its own copy; keep the best</label>
        <div class="cklist">${agentChecks('nm-pa')}</div>
      </div>

      <div id="nm-m-orch">
        <label>Agents the orchestrator may put in its plan</label>
        <div class="cklist" id="nm-oa-list"></div>
        <div class="note" style="color:var(--text-faint)">Tick one project above (the pipeline runs in a copy of it).</div>
      </div>

      <label>Runtime</label>
      <select id="nm-runtime">
        <option value="opencode">OpenCode</option>
        <option value="claude-code">Claude Code</option>
      </select>
      <div id="nm-model-wrap"><label>Model</label><select id="nm-model">${modelOpts}</select></div>
      <div class="note" id="nm-rec" style="color:var(--text-muted)"></div>
      <div class="note" id="nm-claude-note" style="display:none;color:var(--text-faint)">Same agent/persona, same worktree/diff/APPLY flow — just runs on the claude CLI instead of opencode. Uses claude's own default model unless you pin one below.</div>
      <label>AUTONOMY — how much it interrupts you</label>
      <div class="dial" id="nm-dial"><button type="button" data-a="ask">ASK FIRST</button><button type="button" data-a="plan" class="on">PLAN,<br>THEN WAIT</button><button type="button" data-a="auto">RUN &amp;<br>REVIEW</button></div>
      <div class="note" id="nm-dial-hint" style="color:var(--text-muted)"></div>
      <div class="row" style="margin-top:16px">
        <button class="btn go" id="nm-go">START ASK</button>
        <button class="btn" onclick="$('pane').style.display='none';$('hollow').style.display='flex'">cancel</button>
      </div>
    </div>`;

  const kindNow = () => document.querySelector('input[name=nm-kind]:checked').value;
  function renderTeam(){
    $('nm-teamlist').innerHTML = TEAM.map((a,i)=>`<div class="chip">
      <span>${i+1}. ${esc(a)}</span>
      <button type="button" data-i="${i}" data-op="up" ${i===0?'disabled':''}>↑</button>
      <button type="button" data-i="${i}" data-op="dn" ${i===TEAM.length-1?'disabled':''}>↓</button>
      <button type="button" data-i="${i}" data-op="rm">${ic('x')}</button></div>`).join('') || '<span style="color:var(--text-faint)">add at least one</span>';
    $('nm-teamlist').querySelectorAll('button').forEach(b=>b.onclick=()=>{
      const i=+b.dataset.i, op=b.dataset.op;
      if(op==='rm') TEAM.splice(i,1);
      else if(op==='up'&&i>0){ [TEAM[i-1],TEAM[i]]=[TEAM[i],TEAM[i-1]]; }
      else if(op==='dn'&&i<TEAM.length-1){ [TEAM[i+1],TEAM[i]]=[TEAM[i],TEAM[i+1]]; }
      renderTeam();
    });
  }
  renderTeam();
  $('nm-teamplus').onclick = () => { TEAM.push($('nm-teamadd').value); renderTeam(); };

  function renderOrchAgents(){
    const prof = PROFILES[$('nm-profile').value] || {}; const ro = prof.roster || workers.map(a=>a.name);
    $('nm-prof-hint').textContent = prof.hint || '';
    $('nm-oa-list').innerHTML = workers.filter(a=>ro.includes(a.name)).map(a=>
      `<label class="ck" title="${esc(a.description||'')}"><input type="checkbox" class="nm-oa" value="${esc(a.name)}" checked> ${esc(a.name)}</label>`).join('') || '<span style="color:var(--text-faint)">no agents</span>';
  }
  $('nm-profile').onchange = renderOrchAgents; renderOrchAgents();
  function syncMode(){
    const k = kindNow();
    $('nm-m-single').style.display   = k==='single'?'block':'none';
    $('nm-m-team').style.display     = k==='team'?'block':'none';
    $('nm-m-parallel').style.display = k==='parallel'?'block':'none';
    $('nm-m-orch').style.display     = k==='orchestrator'?'block':'none';
    const multi = k==='orchestrator';
    if(PMODE==='existing'){
      $('nm-proj').style.display   = multi?'none':'block';
      $('nm-pmulti').style.display = multi?'flex':'none';
      $('nm-phint').textContent = multi ? 'tick every project the orchestrator may touch' : '';
    }
  }
  document.querySelectorAll('input[name=nm-kind]').forEach(r=>r.onchange=syncMode);
  $('nm-runtime').onchange = () => {
    const isClaude = $('nm-runtime').value === 'claude-code';
    $('nm-model-wrap').style.display = isClaude ? 'none' : 'block';
    $('nm-claude-note').style.display = isClaude ? 'block' : 'none';
  };
  document.querySelectorAll('.nm-pm').forEach(btn=>btn.onclick=()=>{
    PMODE = btn.dataset.pm;
    document.querySelectorAll('.nm-pm').forEach(b=>b.classList.toggle('sel', b===btn));
    $('nm-pex').style.display  = PMODE==='existing'?'block':'none';
    $('nm-pnew').style.display = PMODE==='new'?'block':'none';
    syncMode();
  });
  syncMode();
  const showRec = () => { const k = kindNow();
    let h = recFor(k==='orchestrator' ? 'orchestrator' : ($('nm-agent').value||'coder'));
    if(k==='orchestrator'){ const ro = ((PROFILES[$('nm-profile').value]||{}).roster)||[];
      h += '<div style="margin-top:6px;font-size:11px">Per-agent suggestions (apply with "use suggested" at RUN PIPELINE): ' +
        ro.filter(a=>recPick(a)).map(a=>`<b>${esc(a)}</b> → ${esc(recPick(a).replace(/^opencode\//,'').replace(/^ollama\//,'local:'))}`).join(' · ') + '</div>'; }
    $('nm-rec').innerHTML = h; };
  $('nm-profile').addEventListener('change', showRec);
  $('nm-agent').addEventListener('change', showRec);
  document.querySelectorAll('input[name=nm-kind]').forEach(r=>r.addEventListener('change', showRec));
  loadRecs().then(showRec);

  const DIALHINT = {ask:'It always asks you clarifying questions before planning.', plan:'It plans, then waits for you to press RUN PIPELINE. Applying is always yours.', auto:'It plans and runs by itself, then waits at REVIEW. Applying is always yours.'};
  let AUT = 'plan'; try { AUT = localStorage.getItem('mx_auto') || 'plan'; } catch(e) {}
  const setAut = (a) => { AUT = DIALHINT[a] ? a : 'plan'; document.querySelectorAll('#nm-dial button').forEach(b => b.classList.toggle('on', b.dataset.a===AUT)); $('nm-dial-hint').textContent = DIALHINT[AUT]; try { localStorage.setItem('mx_auto', AUT); } catch(e) {} };
  document.querySelectorAll('#nm-dial button').forEach(b => b.onclick = () => setAut(b.dataset.a)); setAut(AUT);
  $('nm-go').onclick = async () => {
    const k = kindNow();
    const brief = $('nm-brief').value.trim();
    if(!brief){ $('nm-brief').focus(); return; }

    // projects
    let projects = [];
    if(PMODE==='new'){
      const nn = ($('nm-newname').value||'').trim();
      if(!nn){ $('nm-newname').focus(); return; }
      projects = ['new:'+nn];
    } else if(k==='orchestrator'){
      projects = [...document.querySelectorAll('.nm-pcheck:checked')].map(c=>c.value);
      if(!projects.length){ toast('tick at least one project','err'); return; }
    } else {
      projects = [$('nm-proj').value];
    }

    const runtime = $('nm-runtime').value;
    const body = { brief, kind:k, projects, runtime, profile:$('nm-profile').value, reference:$('nm-ref').checked, autonomy:AUT,
      model: (runtime==='claude-code' ? undefined : ($('nm-model').value||undefined)) };
    if(k==='single')      body.agent  = $('nm-agent').value;
    else if(k==='team')   body.agents = TEAM.slice();
    else if(k==='parallel') body.agents = [...document.querySelectorAll('.nm-pa:checked')].map(c=>c.value);
    else if(k==='orchestrator') body.agents = [...document.querySelectorAll('.nm-oa:checked')].map(c=>c.value);
    if((k==='team'||k==='parallel') && !(body.agents||[]).length){ toast('pick at least one agent','err'); return; }

    $('nm-go').disabled=true;
    try {
      const r = await jpost('/api/missions', body);
      await refresh();
      if(r.id) select(r.id);
      else if(r.missions && r.missions[0]) select(r.missions[0].id);
      else { $('pane').style.display='none'; $('hollow').style.display='flex'; }
    } catch(e){ toast('Dispatch failed: '+e.message,'err'); $('nm-go').disabled=false; }
  };
}
$('btn-new').onclick = () => newMission();
$('sk-save').onclick = saveSkill;
  $('sk-cancel').onclick = $('sk-scrim').onclick = () => { $('sk-scrim').classList.remove('open'); $('sk-modal').classList.remove('open'); };
  $('tr-close').onclick = $('tr-scrim').onclick = closeTr;
window.addEventListener('resize', () => fitPipe());
$('btn-reload').onclick = () => location.reload();
$('btn-arch').onclick = () => { $('arch-scrim').classList.add('open'); $('arch-modal').classList.add('open'); };
$('btn-arch-close').onclick = $('arch-scrim').onclick = () => { $('arch-scrim').classList.remove('open'); $('arch-modal').classList.remove('open'); };
boot();
</script>
__VOICE_WIDGET__
</body></html>
"""


@routes.get("/missions")
async def missions_page(request: web.Request) -> web.Response:
    import json
    try:
        from .features import missions as MM
        MM._reconcile_orphans()
        m0 = [m.summary() for m in sorted(MM.S.m.values(), key=lambda x: x.created, reverse=True)]
    except Exception:
        m0 = []
    body = _HTML.replace("__VOICE_WIDGET__", _WIDGET).replace("__TALK_BUTTON__", TALK_BUTTON).replace("__ORBS_JS__", _ORBS_JS).replace("__M0_JSON__", json.dumps(m0).replace("</", "<\\/"))
    return web.Response(text=body, content_type="text/html", charset="utf-8")
