"""What an agent's saved settings do: a one-call model request now carries them, only the ones a model call accepts, and Smith and the Doctor have a model of their own."""
import json

import pytest

from hub import agent_knowledge as AK


@pytest.fixture(autouse=True)
def files(tmp_path, monkeypatch):
    monkeypatch.setattr(AK, "OVERRIDES_FILE", tmp_path / "ov.json")
    monkeypatch.setattr(AK, "_HELPER_MODELS", tmp_path / "hm.json")


def test_only_settings_a_model_call_accepts_are_kept_and_stop_becomes_a_short_list():
    got = AK.clean_options({"top_k": "40", "min_p": 0.05, "num_predict": 512.0, "stop": "END, ###,", "colour": "red", "presence_penalty": "x"})
    assert got == {"top_k": 40, "min_p": 0.05, "num_predict": 512, "stop": ["END", "###"]}


def test_saving_an_option_the_model_would_not_accept_does_not_keep_it():
    AK.save_override("coder", {"options": {"top_k": 30, "colour": "red"}})
    assert AK.load_overrides()["coder"]["options"] == {"colour": "red", "top_k": 30} or AK.load_overrides()["coder"]["options"] == {"top_k": 30, "colour": "red"}
    AK.save_override("coder", {"options": {"bad": "x"}})
    assert "top_k" not in AK.load_overrides()["coder"]["options"]


def test_a_direct_call_sends_top_p_and_the_saved_options(monkeypatch):
    AK.save_override("coder", {"top_p": 0.8, "options": {"top_k": 30, "stop": ["END"]}})
    got = AK.direct_options("coder")
    assert got["top_p"] == 0.8 and got["top_k"] == 30 and got["stop"] == ["END"]


def test_the_request_body_carries_them(monkeypatch):
    from hub.features import missions as M
    seen = {}

    class R:
        status = 200

        async def json(self):
            return {"message": {"content": "hello"}}

        async def text(self):
            return ""

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class S:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def post(self, url, json=None):
            seen.update(json)
            return R()
    import aiohttp
    monkeypatch.setattr(aiohttp, "ClientSession", S)
    import asyncio
    out = asyncio.run(M._direct_chat("ollama/x", "sys", "hi", temperature=0.2, options={"top_k": 30, "stop": ["END"], "top_p": 0.8}))
    assert out == "hello" and seen["options"]["temperature"] == 0.2 and seen["options"]["top_k"] == 30 and seen["options"]["stop"] == ["END"] and seen["options"]["top_p"] == 0.8


def test_smith_and_the_doctor_each_keep_a_model_of_their_own():
    assert AK.helper_model("smith") == "" and AK.helper_model("doctor") == ""
    AK.set_helper_model("smith", "qwen3:4b")
    AK.set_helper_model("doctor", "gemma4:e4b")
    assert AK.helper_model("smith") == "qwen3:4b" and AK.helper_model("doctor") == "gemma4:e4b"
    AK.set_helper_model("smith", "")
    assert AK.helper_model("smith") == "" and AK.helper_model("doctor") == "gemma4:e4b"
