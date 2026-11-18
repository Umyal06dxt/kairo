import time

import pytest
from fastapi.testclient import TestClient

from kairo.server.app import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app(load_voice=False, experiment_dir=tmp_path / "exp")
    with TestClient(app) as c:
        yield c


def drain_until(ws, kind, limit=200):
    seen = []
    for _ in range(limit):
        m = ws.receive_json()
        seen.append(m)
        if m["t"] == kind:
            return m, seen
    raise AssertionError(f"never saw {kind!r}; got {[m['t'] for m in seen][-10:]}")


HELLO = {"t": "hello", "settings": {"domain": "bank", "profile": "reactive", "embedder": "hash",
                                    "llm": "extractive", "distractors": False,
                                    "store_latency_ms": 5}}


def test_info_and_index(client):
    info = client.get("/api/info").json()
    assert {d["key"] for d in info["domains"]} == {"bank", "novacrm"}
    assert "optimized" in {p["key"] for p in info["profiles"]}
    assert client.get("/").status_code == 200


def test_call_lifecycle_over_websocket(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json(HELLO)
        ready, _ = drain_until(ws, "ready")
        assert ready["board"]["n_chunks"] >= 20 and ready["llm"] == "extractive"
        assert ready["domain"]["key"] == "bank" and len(ready["domain"]["scenarios"]) == 10
        assert ready["config"]["strategy"] == "none"
        ws.send_json({"t": "say", "text": "How much is the overdraft fee?"})
        turn, seen = drain_until(ws, "turn")
        kinds = [m["t"] for m in seen]
        assert kinds[0] in ("cache", "status", "turn_start") and "turn_start" in kinds
        assert "token" in kinds
        assert turn["source"] == "store" and turn["hit"] is False and turn["user_ms"] > 0
        assert turn["gold"]["doc_ok"] is True and turn["gold"]["answer_ok"] is None  # no real LLM
        assert turn["stats"]["turns"] == 1
        cache, _ = drain_until(ws, "cache")
        assert cache["entries"] and {e["tag"] for e in cache["entries"]} == {"miss"}


def test_partial_speculation_lights_lamps_before_the_question_arrives(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({**HELLO, "settings": {**HELLO["settings"], "profile": "neighbors"}})
        drain_until(ws, "ready")
        ws.send_json({"t": "partial", "text": "what does the overdraft fee cost"})
        deadline = time.time() + 5
        while time.time() < deadline:
            m = ws.receive_json()
            if m["t"] == "cache" and any(e["tag"] == "partial" for e in m["entries"]):
                return
        raise AssertionError("no partial lamps lit")


def test_baseline_profile_has_no_cache(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({**HELLO, "settings": {**HELLO["settings"], "profile": "baseline"}})
        ready, _ = drain_until(ws, "ready")
        assert ready["profile"]["cache"] is False
        ws.send_json({"t": "say", "text": "What is the overdraft fee?"})
        turn, _ = drain_until(ws, "turn")
        assert turn["source"] == "store" and turn["answer"]


def test_scripted_call_plays_and_reports_gold(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json(HELLO)
        ready, _ = drain_until(ws, "ready")
        scenario = ready["domain"]["scenarios"][1]["key"]  # "B2 Fees"
        ws.send_json({"t": "autoplay", "scenario": scenario})
        start, _ = drain_until(ws, "autoplay")
        assert start["state"] == "start"
        turn, _ = drain_until(ws, "turn")
        assert turn["gold"] is not None
        ws.send_json({"t": "stop"})
        stopped, _ = drain_until(ws, "autoplay")
        assert stopped["state"] in ("stopped", "done")


def test_audio_without_stt_gives_a_helpful_error(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json(HELLO)
        drain_until(ws, "ready")
        ws.send_json({"t": "audio", "data": "AAAA", "mime": "audio/webm"})
        err, _ = drain_until(ws, "error")
        assert "Speech recognition" in err["message"]


def test_experiment_api_validation_and_offline_run(client):
    bad = client.post("/api/experiments", json={"domain": "nope"})
    assert bad.status_code == 400 and "domain" in bad.json()["error"]
    live = client.post("/api/experiments", json={"domain": "bank", "profiles": ["paper"],
                                                 "embedder": "hash", "llm": "openai"})
    assert live.status_code == 400  # needs key + confirm
    ok = client.post("/api/experiments", json={"domain": "bank", "profiles": ["baseline", "reactive"],
                                               "embedder": "hash", "llm": "extractive"})
    assert ok.status_code == 200
    rid = ok.json()["id"]
    for _ in range(150):
        cur = client.get("/api/experiments").json()["current"]
        if cur["state"] != "running":
            break
        time.sleep(0.2)
    assert cur["state"] == "done", cur
    assert set(cur["result"]["profiles"]) == {"baseline", "reactive"}
    saved = client.get("/api/experiments").json()["saved"]
    assert saved and saved[0]["id"] == rid and "markdown" in saved[0]
