"""What a fine-tune of tev would be trained on, and whether it can be started. Nothing here trains anything or touches the GPU.

The data is every graded request after the fresh start (a RIGHT keeps the bin tev chose; a WRONG that names a bin uses that bin), split by the same fixed hash as the held-out set:
the held-out part is never trained on and is what a fine-tuned model is judged on. The objective is the average of minus the log of the probability it gives the right bin, plus a
small penalty on how far the adapter's numbers move; nothing is written by hand. `plan()` says how many rows there are, whether that is enough (100), and what hardware this PC
reports, so you can decide before anything runs. `export()` writes the two files a trainer would read.
"""
from __future__ import annotations

import json

from aiohttp import web

from ..runtime import STATE

routes = web.RouteTableDef()
NEEDED = 100
DIR = STATE / "data" / "yard" / "tev"


def split() -> "tuple[list[dict], list[dict]]":
    from . import fitness as FIT, router_challenger as RC
    train, held = [], []
    for e in RC.examples():
        (held if FIT.held_out(e["text"]) else train).append({"text": e["text"], "label": e["label"]})
    return train, held


def hardware() -> dict:
    out = {"torch": None, "cuda": False, "note": ""}
    try:
        import torch
        out.update(torch=torch.__version__, cuda=bool(torch.cuda.is_available()))
    except Exception:  # noqa: BLE001
        out["note"] = "PyTorch is not installed here"
    if not out["cuda"] and not out["note"]:
        out["note"] = "PyTorch reports no CUDA device (an AMD card needs another route, such as ROCm or DirectML, which a 4B adapter run has not been set up for)"
    return out


def plan() -> dict:
    train, held = split()
    n = len(train) + len(held)
    return {"rows": n, "train": len(train), "held_out": len(held), "needed": NEEDED, "enough": n >= NEEDED, "hardware": hardware(),
            "objective": "minimise -(1/n) sum log p(right bin | sentence) + lambda |adapter|^2 over the training rows; judged on the held-out rows against the nearest-neighbour yardstick and the classifier",
            "output": str(DIR / "adapter"), "note": "Nothing runs until you say go. With fewer than %d graded requests a fine-tune would memorise them." % NEEDED}


def export() -> dict:
    train, held = split()
    DIR.mkdir(parents=True, exist_ok=True)
    for name, rows in (("train.jsonl", train), ("held_out.jsonl", held)):
        (DIR / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return {"train": len(train), "held_out": len(held), "folder": str(DIR)}


@routes.get("/api/yard/tev")
async def api_tev(request: web.Request) -> web.Response:
    return web.json_response(plan())


@routes.post("/api/yard/tev/export")
async def api_tev_export(request: web.Request) -> web.Response:
    return web.json_response(export())
