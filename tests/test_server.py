"""Server, protocol and secret-link access tests (BRIEF 4.1). Starts a real uvicorn on a free port."""
from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
import websockets

TOKEN_A = "tokA_" + "x" * 40
TOKEN_B = "tokB_" + "y" * 40


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    d = tmp_path_factory.mktemp("secrets")
    tokens = d / "tokens.yaml"
    tokens.write_text(f"ana: {TOKEN_A}\nbea: {TOKEN_B}\n")
    os.environ["MOSCA_TOKENS"] = str(tokens)
    os.environ["MOSCA_HMAC_KEY"] = "test-key-0123456789abcdef"
    os.environ.pop("MOSCA_DEBUG", None)
    import uvicorn

    from mosca.server import create_app
    gated, app = create_app()
    port = _free_port()
    cfg = uvicorn.Config(gated, host="127.0.0.1", port=port, log_level="warning", ws="websockets-sansio",
                         server_header=False, date_header=False)
    srv = uvicorn.Server(cfg)
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield {"port": port, "tokens": tokens, "app": app, "base": f"http://127.0.0.1:{port}"}
    srv.should_exit = True
    th.join(timeout=5)


def login(server, token=TOKEN_A, ip="10.0.0.1"):
    r = httpx.get(server["base"] + f"/?k={token}", headers={"cf-connecting-ip": ip}, follow_redirects=False)
    return r


def cookie_of(r):
    sc = r.headers.get("set-cookie", "")
    return sc.split(";")[0]


def test_no_token_identical_404(server):
    paths = ["/", "/ws", "/app.js", "/style.css", "/no/existe", "/health-internal"]
    rs = [httpx.get(server["base"] + p, headers={"cf-connecting-ip": "10.9.9.9"}) for p in paths]
    rs.append(httpx.post(server["base"] + "/", headers={"cf-connecting-ip": "10.9.9.9"}))
    first = rs[0]
    assert first.status_code == 404
    for r in rs:
        assert r.status_code == 404
        assert r.content == first.content
        assert sorted(r.headers.items()) == sorted(first.headers.items())
    h = first.headers
    assert h["x-robots-tag"].startswith("noindex") and h["cache-control"] == "no-store"
    assert "default-src 'self'" in h["content-security-policy"] and h["referrer-policy"] == "no-referrer"
    assert h["x-content-type-options"] == "nosniff"


def test_ws_upgrade_without_cookie_is_404(server):
    async def go():
        url = f"ws://127.0.0.1:{server['port']}/ws"
        with pytest.raises(Exception) as ei:
            async with websockets.connect(url, origin=f"http://127.0.0.1:{server['port']}"):
                pass
        assert "404" in str(ei.value)
    asyncio.run(go())


def test_valid_token_sets_cookie_and_redirects(server):
    r = login(server, ip="10.0.0.2")
    assert r.status_code == 302 and r.headers["location"] == "/"
    sc = r.headers["set-cookie"]
    for attr in ("HttpOnly", "Secure", "SameSite=Lax", "Max-Age=2592000"):
        assert attr in sc
    ok = httpx.get(server["base"] + "/", headers={"cookie": cookie_of(r)})
    assert ok.status_code == 200 and "EXP-DM20K" in ok.text
    js = httpx.get(server["base"] + "/app.js", headers={"cookie": cookie_of(r)})
    assert js.status_code == 200 and "text/javascript" in js.headers["content-type"]


def test_invalid_token_404(server):
    r = login(server, token="nope" * 10, ip="10.0.0.3")
    assert r.status_code == 404


def test_revoked_and_rotated_token(server):
    r = login(server, token=TOKEN_B, ip="10.0.0.4")
    ck = cookie_of(r)
    assert httpx.get(server["base"] + "/", headers={"cookie": ck}).status_code == 200
    tokens = server["tokens"]
    original = tokens.read_text()
    tokens.write_text(f"ana: {TOKEN_A}\n")  # revoke bea
    time.sleep(1.2)
    assert httpx.get(server["base"] + "/", headers={"cookie": ck, "cf-connecting-ip": "10.0.0.44"}).status_code == 404
    tokens.write_text(f"ana: {TOKEN_A}\nbea: {'z' * 40}\n")  # rotate bea
    time.sleep(1.2)
    assert httpx.get(server["base"] + "/", headers={"cookie": ck, "cf-connecting-ip": "10.0.0.45"}).status_code == 404
    assert login(server, token=TOKEN_B, ip="10.0.0.46").status_code == 404
    tokens.write_text(original)
    time.sleep(1.2)


def test_rate_limit_blocks_valid_token(server):
    ip = "10.7.7.7"
    for _ in range(10):
        assert login(server, token="bad" * 12, ip=ip).status_code == 404
    assert login(server, token=TOKEN_A, ip=ip).status_code == 404
    assert login(server, token=TOKEN_A, ip="10.7.7.8").status_code == 302


def _ws_session(server, ip, fn):
    r = login(server, ip=ip)
    ck = cookie_of(r)

    async def go():
        url = f"ws://127.0.0.1:{server['port']}/ws"
        async with websockets.connect(url, origin=f"http://127.0.0.1:{server['port']}",
                                      additional_headers={"cookie": ck}) as ws:
            return await fn(ws)
    return asyncio.run(go())


def test_ws_bad_origin_rejected(server):
    r = login(server, ip="10.0.0.5")

    async def go():
        url = f"ws://127.0.0.1:{server['port']}/ws"
        with pytest.raises(Exception):
            async with websockets.connect(url, origin="https://evil.example",
                                          additional_headers={"cookie": cookie_of(r)}) as ws:
                await asyncio.wait_for(ws.recv(), 2)
    asyncio.run(go())


def test_ws_protocol_orders_and_limits(server):
    async def fn(ws):
        hello = json.loads(await asyncio.wait_for(ws.recv(), 5))
        assert hello["t"] == "hello" and hello["me"] == "ana" and hello["arena"] == [2160, 1620]
        assert {d["id"] for d in hello["drinks"]} == {"beer", "wine", "shot", "tequila", "garrafon"}
        # malformed messages must be ignored
        for junk in ["{", "[]", "null", json.dumps({"t": "drink", "kind": 5}), json.dumps({"t": "x"}), "x" * 2000]:
            await ws.send(junk)
        await ws.send(json.dumps({"t": "reset"}))
        frames, toasts = [], []
        kinds = ["beer", "wine", "shot", "tequila", "garrafon"]
        t_end = time.time() + 12
        sent = 0
        next_order = time.time()
        while time.time() < t_end:
            if sent < 5 and time.time() >= next_order:
                await ws.send(json.dumps({"t": "drink", "kind": kinds[sent]}))
                sent += 1
                next_order = time.time() + 1.6
            m = json.loads(await asyncio.wait_for(ws.recv(), 5))
            if m["t"] == "frame":
                frames.append(m)
            elif m["t"] == "toast":
                toasts.append(m["text"])
        return frames, toasts

    frames, toasts = _ws_session(server, "10.0.0.6", fn)
    assert len(frames) > 150  # ~30 Hz
    f = frames[-1]
    for k in ("n", "a", "stage", "r", "f", "puddles", "fx", "map", "viewers"):
        assert k in f
    assert len(f["map"]) == 24 and all(0 <= v <= 255 for v in f["map"])
    assert set(f["f"]) >= {"x", "y", "th", "z", "v", "w", "pose", "act", "prob", "wing"}
    assert max(len(fr["puddles"]) for fr in frames) <= 3
    assert any("ana sirve" in t for t in toasts)
    # 5 orders while at most 3 puddles fit: at least one "bar full" unless she drank one meanwhile
    assert any("barra está llena" in t for t in toasts) or any(len(fr["puddles"]) < 3 for fr in frames[-60:])


def test_order_rate_limit(server):
    async def fn(ws):
        await asyncio.wait_for(ws.recv(), 5)
        await ws.send(json.dumps({"t": "reset"}))
        await ws.send(json.dumps({"t": "drink", "kind": "beer"}))
        await ws.send(json.dumps({"t": "drink", "kind": "beer"}))
        toasts = []
        t_end = time.time() + 1.0
        while time.time() < t_end:
            m = json.loads(await asyncio.wait_for(ws.recv(), 5))
            if m["t"] == "toast":
                toasts.append(m["text"])
        return toasts
    time.sleep(1.6)
    toasts = _ws_session(server, "10.0.0.7", fn)
    assert any("Espera" in t for t in toasts) or any("barra está llena" in t for t in toasts)


def test_pauses_without_clients(server):
    hub = server["app"].state.hub
    time.sleep(0.6)
    assert hub is not None and len(hub.clients) == 0 and hub.running is False
    t0 = hub.ticks
    time.sleep(1.0)
    assert hub.ticks == t0


def test_help_up_puts_a_fallen_fly_on_its_feet():
    from mosca.live import Live
    live = Live(seed=3)
    live.sim.world.fly.pose = "back"
    live.sim.body.pose = "back"
    live.help_up()
    assert live.sim.world.fly.pose == "up" and live.sim.body.pose == "up" and "helpup" in live.pending_fx
