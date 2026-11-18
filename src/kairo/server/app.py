"""Web lab: serves the UI, a websocket per call, and an experiments API."""

import asyncio
import contextlib
import json
import os
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..bench.domains import DOMAIN_KEYS, get_domain
from ..bench.run import PROFILES, format_experiment, run_experiment
from .session import EMBEDDERS, Session, Shared

STATIC = Path(__file__).parent / "static"  # the React build (web/) is written here
EXPERIMENT_DIR = Path("data/experiments")

FALLBACK_HTML = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kairo lab</title>
<body style="font:16px/1.6 system-ui,sans-serif;max-width:560px;margin:12vh auto;padding:0 20px;color:#14141a">
<h1 style="margin:0 0 8px">Kairo lab is running, but the web UI isn't built yet</h1>
<p>The server is healthy. The interface is a React app that needs a one-time build:</p>
<pre style="background:#f1eef7;padding:14px;border-radius:10px;overflow-x:auto">cd web
npm install
npm run build</pre>
<p>Then reload this page. For live-reload development, run <code>npm run dev</code> in <code>web/</code>
(it proxies to this server). The API is available now at <a href="/api/info">/api/info</a>.</p></body></html>"""


class Experiments:
    """Runs one experiment at a time; results are saved as JSON so they survive restarts."""

    def __init__(self, directory: Path = EXPERIMENT_DIR):
        self.dir = directory
        self.current: dict | None = None
        self._task: asyncio.Task | None = None

    def saved(self) -> list[dict]:
        out = []
        for p in sorted(self.dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                d = json.loads(p.read_text())
                out.append({"id": p.stem, **d})
            except (OSError, ValueError):
                continue
        return out

    def start(self, spec: dict) -> tuple[bool, str]:
        if self._task and not self._task.done():
            return False, "An experiment is already running."
        err = self._validate(spec)
        if err:
            return False, err
        rid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        self.current = {"id": rid, "state": "running", "progress": ["starting…"], "spec": spec}
        self._task = asyncio.create_task(self._run(rid, spec))
        return True, rid

    @staticmethod
    def _validate(spec: dict) -> str | None:
        if spec.get("domain") not in DOMAIN_KEYS:
            return f"domain must be one of {DOMAIN_KEYS}"
        profiles = spec.get("profiles") or []
        if not profiles or any(p not in PROFILES for p in profiles):
            return f"profiles must be a non-empty subset of {sorted(PROFILES)}"
        if spec.get("embedder") not in EMBEDDERS or spec.get("llm") not in ("extractive", "openai"):
            return "embedder must be local/openai/hash and llm extractive/openai"
        live = spec["llm"] == "openai" or spec["embedder"] == "openai"
        if live and not os.environ.get("OPENAI_API_KEY"):
            return "This run uses the OpenAI API, but no OPENAI_API_KEY is set."
        if live and not spec.get("confirm"):
            return "This run calls the OpenAI API and costs a few cents. Confirm to start."
        return None

    async def _run(self, rid: str, spec: dict) -> None:
        cur = self.current
        try:
            res = await run_experiment(
                spec["domain"], spec["profiles"], embedder=spec["embedder"], llm=spec["llm"],
                generate=spec["llm"] == "openai", distractors=min(int(spec.get("distractors", 0)), 64),
                sweep_profile=spec.get("sweep") or None, llm_ttft_s=0.4,
                progress=lambda m: cur["progress"].append(m))
            payload = {**res.to_json(), "generated": time.strftime("%Y-%m-%d %H:%M"),
                       "markdown": format_experiment(res)}
            self.dir.mkdir(parents=True, exist_ok=True)
            (self.dir / f"{rid}.json").write_text(json.dumps(payload, indent=1))
            cur.update(state="done", result=payload)
        except Exception as e:  # report to the UI instead of dying silently
            cur.update(state="error", error=f"{type(e).__name__}: {e}")


def create_app(whisper: str = "base.en", load_voice: bool = True,
               experiment_dir: Path = EXPERIMENT_DIR, static_dir: Path = STATIC) -> FastAPI:
    shared = Shared()
    experiments = Experiments(experiment_dir)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        loader = asyncio.create_task(shared.load_stt(whisper)) if load_voice else None
        yield
        if loader:
            loader.cancel()

    app = FastAPI(title="Kairo lab", lifespan=lifespan)
    app.state.shared, app.state.experiments = shared, experiments

    @app.get("/", response_model=None)
    async def index() -> FileResponse | HTMLResponse:
        page = static_dir / "index.html"
        return FileResponse(page) if page.exists() else HTMLResponse(FALLBACK_HTML)

    @app.get("/api/info")
    async def info() -> dict:
        return {
            "has_key": bool(os.environ.get("OPENAI_API_KEY")),
            "stt": shared.stt_state,
            "domains": [{"key": k, "title": get_domain(k).title, "blurb": get_domain(k).blurb}
                        for k in DOMAIN_KEYS],
            "profiles": [{"key": p.key, "label": p.label, "cache": p.cache,
                          "strategy": p.config.strategy, "verify": p.config.verify_hits,
                          "drafts": p.config.speculative_answers} for p in PROFILES.values()],
        }

    @app.get("/api/experiments")
    async def list_experiments() -> dict:
        return {"saved": experiments.saved(), "current": experiments.current}

    @app.post("/api/experiments")
    async def start_experiment(spec: dict) -> JSONResponse:
        ok, msg = experiments.start(spec)
        return JSONResponse({"ok": ok, "id" if ok else "error": msg}, status_code=200 if ok else 400)

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        session = Session(ws, shared)
        try:
            while True:
                msg = await ws.receive_json()
                kind = msg.get("t")
                if kind == "hello":
                    await session.configure(msg.get("settings", {}))
                elif kind == "say":
                    asyncio.create_task(session.say(str(msg.get("text", ""))))
                elif kind == "partial":
                    await session.partial(str(msg.get("text", "")))
                elif kind == "audio":
                    asyncio.create_task(session.audio(msg.get("data", ""), msg.get("mime", "")))
                elif kind == "autoplay":
                    await session.autoplay(str(msg.get("scenario", "")))
                elif kind == "stop":
                    await session.stop_autoplay()
        except WebSocketDisconnect:
            pass
        finally:
            await session.close()

    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    return app


async def serve(args) -> None:
    import uvicorn
    app = create_app(args.whisper, load_voice=not args.no_voice)
    config = uvicorn.Config(app, host=args.host, port=args.port, log_level="warning")
    print(f"Kairo lab → http://{args.host}:{args.port}   (Ctrl-C to stop)")
    await uvicorn.Server(config).serve()
