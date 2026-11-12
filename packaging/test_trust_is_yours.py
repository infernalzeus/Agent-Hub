"""Trust is a person's decision. No number of clean runs promotes a routine; PROMOTE and DEMOTE set it, and a demotion sticks."""
import asyncio
import sqlite3

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from hub.features import pc_control as PC


def _add(status="candidate", successes=0, rid="r1", intent="open:notepad"):
    with PC._db() as db:
        db.execute("INSERT INTO pc_routines (id,intent,title,tool,kind,args_json,signature_json,status,successes,failures,created,updated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (rid, intent, "Open Notepad", "App", "mcp", "{}", "{}", status, successes, 0, 1.0, 1.0))


def _status(rid="r1"):
    with PC._db() as db:
        return db.execute("SELECT status, approved FROM pc_routines WHERE id=?", (rid,)).fetchone()["status"]


def test_clean_runs_add_up_but_never_promote():
    _add()
    for _ in range(5):
        PC._remember_outcome("r1", True)
    assert _status() == "candidate"                                                                 # five clean runs, and reopening the database changes nothing
    with PC._db() as db:
        assert db.execute("SELECT successes FROM pc_routines WHERE id='r1'").fetchone()["successes"] == 5


def test_promote_and_demote_work_from_the_status_endpoint_and_a_demotion_sticks_after_many_clean_runs():
    _add(successes=20)
    app = web.Application()
    app.add_routes(PC.routes)

    async def go():
        async with TestClient(TestServer(app)) as c:
            assert (await c.post("/api/pc/routines/r1/status", json={"status": "trusted"})).status == 200
            assert _status() == "trusted"
            assert (await c.post("/api/pc/routines/r1/status", json={"status": "candidate"})).status == 200
            assert _status() == "candidate"                                                          # 20 clean runs would once have promoted it again on the next open
            assert _status() == "candidate"
            assert (await c.post("/api/pc/routines/r1/status", json={"status": "bogus"})).status == 400
    asyncio.run(go())


def test_what_the_old_automatic_promotion_granted_is_withdrawn_once_and_an_approval_after_that_stays():
    PC.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(PC.DB_PATH)                                                               # a database as it was: no 'approved' column, three routines promoted by their counts
    conn.execute("CREATE TABLE pc_routines (id TEXT PRIMARY KEY, intent TEXT NOT NULL UNIQUE, title TEXT NOT NULL, tool TEXT NOT NULL, args_json TEXT NOT NULL DEFAULT '{}', "
                 "signature_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'candidate', successes INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0, "
                 "created REAL NOT NULL, updated REAL NOT NULL, kind TEXT NOT NULL DEFAULT 'mcp')")
    for i, name in enumerate(("claude", "apple music", "notepad")):
        conn.execute("INSERT INTO pc_routines (id,intent,title,tool,status,successes,created,updated) VALUES (?,?,?,?,?,?,?,?)", (f"o{i}", f"open:{name}", f"Open {name}", "App", "trusted", 20, 1.0, 1.0))
    conn.commit()
    conn.close()
    with PC._db() as db:
        got = [r["status"] for r in db.execute("SELECT status FROM pc_routines ORDER BY id")]
    assert got == ["candidate"] * 3                                                                  # all candidates, as they should always have been
    app = web.Application()
    app.add_routes(PC.routes)

    async def go():
        async with TestClient(TestServer(app)) as c:
            assert (await c.post("/api/pc/routines/o0/status", json={"status": "trusted"})).status == 200
    asyncio.run(go())
    with PC._db() as db:
        assert {r["id"]: r["status"] for r in db.execute("SELECT id,status FROM pc_routines")} == {"o0": "trusted", "o1": "candidate", "o2": "candidate"}   # the migration ran once: your approval is kept


def test_promoting_clears_the_failures_held_against_a_routine_and_a_good_attempt_ends_a_run_of_them():
    from hub.features import run_record as RR
    import tempfile, pathlib
    RR.STATE = pathlib.Path(tempfile.mkdtemp())
    _add(rid="r7", intent="open:claude")
    RR.note_outcome("r7", False)
    RR.note_outcome("r7", False)
    assert RR.trailing_failures("r7") == 2
    app = web.Application()
    app.add_routes(PC.routes)

    async def go():
        async with TestClient(TestServer(app)) as c:
            assert (await c.post("/api/pc/routines/r7/status", json={"status": "trusted"})).status == 200
    asyncio.run(go())
    assert RR.trailing_failures("r7") == 0                                                              # you approved it: the old failures are not held against it
    RR.note_outcome("r7", False)
    RR.note_outcome("r7", True)
    assert RR.trailing_failures("r7") == 0                                                              # a success ends the run of failures
