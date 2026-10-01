"""The colours every page uses, in one place, so they can be changed.

Each page grew its own `:root` block with the same values typed again, which made
a colour change a search-and-replace across six files and made a *theme*
impossible. This serves one stylesheet that every page links last, so whatever it
says wins over the block the page still carries - no page had to be rewritten to
gain theming, and a page with no network to this route still renders in the
default colours rather than unstyled.

Only the colours that carry meaning are listed. The hub's pages contain ~78 hex
literals, but most are one-off tints; these twelve are the ones used repeatedly
and the ones a theme actually decides. Everything else derives from `accent` at
an alpha - which is why changing one value re-tints text, borders and glow
together instead of leaving half the page green.
"""
from __future__ import annotations

import json

from aiohttp import web

from .config import logger
from .runtime import STATE, write_json

routes = web.RouteTableDef()

FILE = STATE / "theme.json"

# key, label, default, what it actually controls
TOKENS: "list[tuple[str, str, str, str]]" = [
    ("accent",     "Accent",            "#00e676", "Highlights, buttons, borders and all green text"),
    ("ink",        "Bright text",       "#d9ffe9", "Headings and values that must stay readable"),
    ("bg",         "Background",        "#080c28", "The darkest corner of the page"),
    ("bg_mid",     "Background middle", "#0d1050", "Middle of the page gradient"),
    ("bg_far",     "Background far",    "#18095c", "Far end of the gradient - the purple cast"),
    ("bg_deep",    "Card interior",     "#0a0c3e", "Inside inputs and nested panels"),
    ("panel",      "Panel",             "#080c28", "Card and panel fill, laid over the gradient"),
    ("red",        "Danger",            "#ff5c5c", "Failures, destructive buttons"),
    ("amber",      "Waiting",           "#e0a53c", "Paused, stopped, waiting for you"),
    ("purple",     "Purple",            "#b07cd6", "Second accent, graph categories"),
    ("blue",       "Blue",              "#3ba7ff", "Suggestions and links"),
    ("grey",       "Muted",             "#6f8f80", "Disabled and faint text"),
]

DEFAULTS = {k: d for k, _l, d, _w in TOKENS}

# Named themes. "custom" is not here: it is whatever the user saved, and only
# exists once they have saved something.
THEMES: "dict[str, dict]" = {
    "default": {"label": "Default", "note": "Green on deep navy - the hub as built.",
                "colors": dict(DEFAULTS)},
}


def _read() -> dict:
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def current() -> dict:
    """{name, colors} - always complete, even if the file is partial or absent."""
    saved = _read()
    name = saved.get("name") or "default"
    if name == "custom":
        colors = {**DEFAULTS, **(saved.get("custom") or {})}
    else:
        colors = {**DEFAULTS, **(THEMES.get(name, THEMES["default"])["colors"])}
    return {"name": name, "colors": colors, "custom": saved.get("custom") or dict(DEFAULTS)}


def save(name: str, colors: "dict | None" = None) -> dict:
    if name != "custom" and name not in THEMES:
        raise ValueError(f"no theme called {name!r}")
    data = _read()
    data["name"] = name
    if name == "custom":
        clean = {k: v for k, v in (colors or {}).items() if k in DEFAULTS and _ok(v)}
        if not clean:
            raise ValueError("a custom theme needs at least one colour")
        data["custom"] = {**DEFAULTS, **clean}
    write_json(FILE, data)
    logger.info("theme: now %s", name)
    return current()


def _ok(v) -> bool:
    """A CSS hex colour and nothing else - this value is interpolated into a
    stylesheet, so anything else would be an injection point."""
    v = str(v or "").strip()
    return bool(v.startswith("#") and len(v) in (4, 7)
                and all(c in "0123456789abcdefABCDEF" for c in v[1:]))


def _rgba(hex_colour: str, alpha: float) -> str:
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def css(colors: "dict | None" = None) -> str:
    """The stylesheet. Text and borders are derived from the accent, so one
    colour change re-tints the page as a whole rather than in patches."""
    c = {**DEFAULTS, **(colors or current()["colors"])}
    a = c["accent"]
    return f""":root{{
  --accent:{a};
  --ink:{c['ink']};
  --bg:{c['bg']};--bg-mid:{c['bg_mid']};--bg-deep:{c['bg_deep']};
  --panel:{_rgba(c['panel'], 0.88)};
  --text:{_rgba(a, 0.90)};--text-muted:{_rgba(a, 0.52)};--text-faint:{_rgba(a, 0.26)};
  --border:{_rgba(a, 0.30)};--border-dim:{_rgba(a, 0.22)};--border-bright:{_rgba(a, 0.55)};
  --red:{c['red']};--amber:{c['amber']};--purple:{c['purple']};--blue:{c['blue']};
  --green:{a};--cyan:{c['blue']};--orange:{c['amber']};--grey:{c['grey']};
}}
html{{background:linear-gradient(150deg,{c['bg']} 0%,{c['bg_mid']} 45%,{c['bg_far']} 100%) fixed}}
"""


@routes.get("/theme.css")
async def theme_css(request: web.Request) -> web.Response:
    # no-store: a theme change must show on the next load, not whenever the
    # browser decides its copy is stale.
    return web.Response(text=css(), content_type="text/css",
                        headers={"Cache-Control": "no-store"})


def _payload() -> dict:
    """What the Settings page needs. Returned by GET *and* PUT, because the page
    re-renders from whatever the call hands back - a PUT that replied with less
    than a GET left it unable to redraw the picker it had just used."""
    cur = current()
    return {
        **cur,
        "tokens": [{"key": k, "label": l, "default": d, "what": w} for k, l, d, w in TOKENS],
        "themes": [{"name": n, "label": t["label"], "note": t["note"]} for n, t in THEMES.items()]
                  + [{"name": "custom", "label": "Custom",
                      "note": "Your own colours - start from the default and change what you like."}],
    }


@routes.get("/api/theme")
async def api_get(request: web.Request) -> web.Response:
    return web.json_response(_payload())


@routes.put("/api/theme")
async def api_put(request: web.Request) -> web.Response:
    body = await request.json()
    try:
        save(str(body.get("name") or "default"), body.get("colors"))
        return web.json_response(_payload())
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))
