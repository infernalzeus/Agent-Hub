"""Board-hosted pages keep their actions but omit duplicate navigation chrome."""
from aiohttp import web


def embedded(body: str, request: web.Request) -> str:
    if request.query.get("embed") != "1":
        return body
    css = """<style id="hub-embed-style">
html.hub-embed .bar>a,html.hub-embed .bar>.brand,html.hub-embed body>header,
html.hub-embed body>h1{display:none!important}
html.hub-embed .bar{padding:8px;position:relative;min-height:0}
html.hub-embed svg#graph{top:0;height:100%}
html.hub-embed #legend{top:14px}
</style>"""
    body = body.replace('<html lang="en">', '<html lang="en" class="hub-embed">', 1)
    if 'class="hub-embed"' not in body:
        body = body.replace('<html>', '<html class="hub-embed">', 1)
    return body.replace('</head>', css + '</head>', 1)
