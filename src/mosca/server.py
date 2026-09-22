"""FastAPI + uvicorn server: one shared simulation at 30 Hz, only while someone is watching.

Env:
  MOSCA_TOKENS        path to tokens.yaml (name: token)            [required]
  MOSCA_HMAC_KEY(_FILE) server secret for cookie signatures          [required]
  MOSCA_DEBUG=1       local only: ?debug_a=&debug_r=&seed=&debug_puddles=1
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response

from .auth import Auth, GateMiddleware, TokenStore, load_key
from .config import ROOT
from .live import Live
from .world import DT

WEB = Path(os.environ.get("MOSCA_WEB", ROOT / "web"))
DEBUG = os.environ.get("MOSCA_DEBUG") == "1"
STATIC = {"/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8"),
          "/": ("index.html", "text/html; charset=utf-8")}


class Client:
    def __init__(self, ws: WebSocket, name: str):
        self.ws = ws
        self.name = name
        self.q: asyncio.Queue = asyncio.Queue(maxsize=3)
        self.dropped = 0

    def offer(self, msg: str, important: bool = False):
        if self.q.full():
            if not important:
                self.dropped += 1
                return
            try:
                self.q.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self.q.put_nowait(msg)


class Hub:
    def __init__(self, live: Live, max_clients: int):
        self.live = live
        self.max_clients = max_clients
        self.clients: set[Client] = set()
        self.wake = asyncio.Event()
        self.task: asyncio.Task | None = None
        self.ticks = 0
        self.tick_ms: list[float] = []
        self.running = False

    def start(self):
        if self.task is None:
            self.task = asyncio.create_task(self.loop())

    def broadcast(self, msg: str, important=False):
        for c in list(self.clients):
            c.offer(msg, important)

    def toast(self, text: str):
        if text:
            self.broadcast(json.dumps({"t": "toast", "text": text}, ensure_ascii=False, separators=(",", ":")), True)

    async def loop(self):
        loop = asyncio.get_running_loop()
        nxt = loop.time()
        while True:
            if not self.clients:
                self.running = False
                self.wake.clear()
                await self.wake.wait()  # paused: no CPU while nobody watches
                nxt = loop.time()
            self.running = True
            t0 = time.perf_counter()
            try:
                self.live.step()
                frame = json.dumps(self.live.frame(len(self.clients)), ensure_ascii=False, separators=(",", ":"))
            except Exception as e:  # never let the loop die
                print("sim error:", repr(e), flush=True)
                await asyncio.sleep(0.5)
                continue
            self.ticks += 1
            self.tick_ms.append((time.perf_counter() - t0) * 1e3)
            if len(self.tick_ms) > 3000:
                self.tick_ms = self.tick_ms[-1500:]
            self.broadcast(frame)
            for t in self.live.take_toasts():
                self.toast(t)
            nxt += DT
            now = loop.time()
            if nxt < now - 0.5:
                nxt = now
            await asyncio.sleep(max(0.0, nxt - now))


def create_app() -> FastAPI:
    tokens = os.environ.get("MOSCA_TOKENS", "/run/mosca-secrets/tokens.yaml")
    auth = Auth(TokenStore(tokens), load_key())
    live = Live()
    ui = live.ui
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.hub = None
    taps: dict[str, float] = {}

    def hub() -> Hub:
        if app.state.hub is None:
            app.state.hub = Hub(live, int(ui.get("max_clients", 20)))
            app.state.hub.start()
        return app.state.hub

    for route, (fname, ctype) in STATIC.items():
        def make(fname=fname, ctype=ctype):
            async def serve():
                return FileResponse(WEB / fname, media_type=ctype)
            return serve
        app.add_api_route(route, make(), methods=["GET"], include_in_schema=False)

    @app.get("/health-internal", include_in_schema=False)
    async def health():
        h = hub()
        ms = sorted(h.tick_ms[-900:]) or [0.0]
        return {"clients": len(h.clients), "running": h.running, "ticks": h.ticks,
                "tick_ms_p50": ms[len(ms) // 2], "tick_ms_p95": ms[int(len(ms) * 0.95)],
                "dropped": sum(c.dropped for c in h.clients)}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        name = ws.scope.get("mosca_user")
        hdr = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in ws.scope.get("headers", [])}
        origin, host = hdr.get("origin", ""), hdr.get("host", "")
        if not name or not origin or urlsplit(origin).netloc.lower() != host.lower():
            await ws.close(code=1008)
            return
        h = hub()
        if len(h.clients) >= h.max_clients:
            await ws.accept()
            await ws.send_text(json.dumps({"t": "toast", "text": "Aforo completo, prueba en un rato"}, ensure_ascii=False))
            await ws.close(code=1013)
            return
        await ws.accept()
        if DEBUG:
            q = parse_qs(ws.scope.get("query_string", b"").decode())
            def num(k):
                try:
                    return float(q[k][0]) if k in q else None
                except ValueError:
                    return None
            if any(k in q for k in ("debug_a", "debug_r", "seed", "debug_puddles")):
                s = num("seed")
                live.set_debug(num("debug_a"), num("debug_r"), int(s) if s is not None else None,
                               q.get("debug_puddles", ["0"])[0] == "1")
        c = Client(ws, name)
        h.clients.add(c)
        h.wake.set()
        c.offer(json.dumps(live.hello(name), ensure_ascii=False, separators=(",", ":")), True)

        async def sender():
            while True:
                msg = await c.q.get()
                await ws.send_text(msg)

        st = asyncio.create_task(sender())
        try:
            while True:
                raw = await ws.receive_text()
                if len(raw) > 512:
                    continue
                try:
                    msg = json.loads(raw)
                    if not isinstance(msg, dict):
                        continue
                    kind = msg.get("t")
                    if kind == "drink" and isinstance(msg.get("kind"), str):
                        ok, text = live.order(msg["kind"], name)
                        if ok:
                            h.toast(text)
                        elif text:
                            c.offer(json.dumps({"t": "toast", "text": text}, ensure_ascii=False), True)
                    elif kind == "tap":
                        now = time.monotonic()
                        if now - taps.get(name, -9.0) >= 3.0:        # once every 3 s per visitor
                            taps[name] = now
                            live.tap()
                    elif kind == "reset":
                        live.reset()
                        h.toast(ui["toasts"]["reset"].format(who=name))
                    elif kind == "demo":
                        if msg.get("on") is True:
                            live.start_demo()
                            h.toast(ui["toasts"]["demo_on"].format(who=name))
                        elif msg.get("on") is False:
                            live.stop_demo()
                except (ValueError, TypeError, KeyError):
                    continue
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            st.cancel()
            h.clients.discard(c)

    @app.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
                   include_in_schema=False)
    async def fallback(path: str):
        return Response(b"Not Found", status_code=404, media_type="text/plain; charset=utf-8")

    app.state.live = live
    return GateMiddleware(app, auth), app


def main():
    import uvicorn
    gated, _ = create_app()
    uvicorn.run(gated, host=os.environ.get("MOSCA_HOST", "0.0.0.0"), port=int(os.environ.get("MOSCA_PORT", "8000")),
                server_header=False, date_header=False, proxy_headers=False, access_log=False,
                ws="websockets-sansio", ws_max_size=4096, log_level="warning")


if __name__ == "__main__":
    main()
