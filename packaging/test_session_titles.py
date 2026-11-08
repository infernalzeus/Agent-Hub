"""A session in the dashboard is named by the session, not by the last thing typed to it."""
import json

from hub.features import agent_sessions as AS


def _file(tmp_path, records):
    p = tmp_path / "s.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return p


def test_the_session_own_title_wins_over_the_latest_prompt(tmp_path):
    p = _file(tmp_path, [{"type": "ai-title", "aiTitle": "Early name"}, {"type": "user", "message": {"content": "it is broken on the desktop hub page"}},
                         {"type": "custom-title", "customTitle": "Agent Hub development and bug fixes"}, {"type": "user", "message": {"content": "now fix the button"}}])
    recs = AS._tail_records(p)
    assert AS._own_title(recs, p) == "Agent Hub development and bug fixes"          # the newest title record
    assert AS._title(recs) == "now fix the button"                                    # the latest prompt is still known, for the status line


def test_a_title_far_back_in_the_file_is_still_found_and_none_gives_empty(tmp_path):
    many = [{"type": "user", "message": {"content": f"turn {i}"}} for i in range(3000)]
    p = _file(tmp_path, [{"type": "custom-title", "customTitle": "Old but named"}] + many)
    assert AS._own_title(AS._tail_records(p), p) == "Old but named"
    q = _file(tmp_path, [{"type": "user", "message": {"content": "hello"}}])
    assert AS._own_title(AS._tail_records(q), q) == ""
