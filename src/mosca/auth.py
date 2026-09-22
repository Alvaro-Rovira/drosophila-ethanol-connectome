"""Secret-link access (BRIEF 3.5).

tokens.yaml (outside the repo) maps name -> token. `/?k=TOKEN` sets a signed cookie
(name + token fingerprint, HMAC-SHA256 with a server key) and redirects to `/`.
Without a valid cookie or token EVERYTHING answers the same 404. Rotating or revoking a
token invalidates old cookies immediately (fingerprint check). 10 failures / 10 min / IP
(CF-Connecting-IP) -> 404 for 10 min even with a valid token.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from collections import defaultdict, deque
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs

import yaml

COOKIE = "mosca_s"
COOKIE_MAX_AGE = 30 * 24 * 3600
FAIL_WINDOW = 600.0
FAIL_MAX = 10
BLOCK_S = 600.0

SEC_HEADERS = [
    (b"x-robots-tag", b"noindex, nofollow"),
    (b"cache-control", b"no-store"),
    (b"content-security-policy",
     b"default-src 'self'; connect-src 'self' wss:; img-src 'self' data:; style-src 'self'; script-src 'self'; "
     b"media-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
]
NOT_FOUND_BODY = b"Not Found"
NOT_FOUND_HEADERS = [(b"content-type", b"text/plain; charset=utf-8"),
                     (b"content-length", str(len(NOT_FOUND_BODY)).encode())] + SEC_HEADERS


def fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:24]


class TokenStore:
    def __init__(self, path: str | Path, check_every: float = 1.0):
        self.path = Path(path)
        self.check_every = check_every
        self._mtime = None
        self._checked = 0.0
        self.tokens: dict[str, str] = {}
        self._reload(force=True)

    def _reload(self, force=False):
        now = time.monotonic()
        if not force and now - self._checked < self.check_every:
            return
        self._checked = now
        try:
            st = self.path.stat()
            key = (st.st_mtime_ns, st.st_size, st.st_ino)
        except FileNotFoundError:
            self.tokens, self._mtime = {}, None
            return
        if key == self._mtime and not force:
            return
        try:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except Exception:
            return  # keep the previous tokens if the file is being rewritten
        self.tokens = {str(k): str(v) for k, v in data.items() if v and len(str(v)) >= 32}
        self._mtime = key

    def name_for(self, token: str) -> str | None:
        self._reload()
        found = None
        tb = token.encode()
        for name, t in self.tokens.items():  # constant time per entry, no early exit
            if hmac.compare_digest(t.encode(), tb):
                found = name
        return found

    def fp(self, name: str) -> str | None:
        self._reload()
        t = self.tokens.get(name)
        return fingerprint(t) if t else None


class RateLimiter:
    def __init__(self):
        self.fails: dict[str, deque] = defaultdict(deque)
        self.blocked: dict[str, float] = {}

    def is_blocked(self, ip: str) -> bool:
        until = self.blocked.get(ip)
        if until and time.monotonic() < until:
            return True
        if until:
            self.blocked.pop(ip, None)
        return False

    def fail(self, ip: str):
        now = time.monotonic()
        q = self.fails[ip]
        q.append(now)
        while q and now - q[0] > FAIL_WINDOW:
            q.popleft()
        if len(q) >= FAIL_MAX:
            self.blocked[ip] = now + BLOCK_S
            q.clear()
        if len(self.fails) > 10000:  # bound memory
            for k in list(self.fails)[:5000]:
                self.fails.pop(k, None)


class Auth:
    def __init__(self, store: TokenStore, key: bytes):
        if len(key) < 16:
            raise ValueError("HMAC key too short")
        self.store = store
        self.key = key
        self.limiter = RateLimiter()

    def _sig(self, payload: str) -> str:
        return hmac.new(self.key, payload.encode(), hashlib.sha256).hexdigest()[:32]

    def make_cookie(self, name: str) -> str:
        fp = self.store.fp(name) or ""
        n = base64.urlsafe_b64encode(name.encode()).decode().rstrip("=")
        payload = f"{n}.{fp}"
        return f"{payload}.{self._sig(payload)}"

    def check_cookie(self, value: str) -> str | None:
        try:
            n, fp, sig = value.split(".")
            if not hmac.compare_digest(sig, self._sig(f"{n}.{fp}")):
                return None
            name = base64.urlsafe_b64decode(n + "=" * (-len(n) % 4)).decode()
        except Exception:
            return None
        cur = self.store.fp(name)
        if not cur or not hmac.compare_digest(cur, fp):
            return None
        return name


def load_key() -> bytes:
    k = os.environ.get("MOSCA_HMAC_KEY")
    if not k and os.environ.get("MOSCA_HMAC_KEY_FILE"):
        k = Path(os.environ["MOSCA_HMAC_KEY_FILE"]).read_text().strip()
    if not k:
        raise RuntimeError("MOSCA_HMAC_KEY or MOSCA_HMAC_KEY_FILE is required")
    return k.encode()


def _headers(scope) -> dict[bytes, bytes]:
    return {k.lower(): v for k, v in scope.get("headers", [])}


def client_ip(scope) -> str:
    h = _headers(scope)
    ip = h.get(b"cf-connecting-ip")
    if ip:
        return ip.decode("latin-1")[:64]
    c = scope.get("client")
    return c[0] if c else "?"


async def send_404(scope, receive, send):
    if scope["type"] == "websocket":
        if "websocket.http.response" in scope.get("extensions", {}):
            await send({"type": "websocket.http.response.start", "status": 404, "headers": NOT_FOUND_HEADERS})
            await send({"type": "websocket.http.response.body", "body": NOT_FOUND_BODY})
        else:
            await send({"type": "websocket.close", "code": 1008})
        return
    await send({"type": "http.response.start", "status": 404, "headers": NOT_FOUND_HEADERS})
    await send({"type": "http.response.body", "body": NOT_FOUND_BODY})


class GateMiddleware:
    """Pure ASGI middleware in front of the whole app."""

    def __init__(self, app, auth: Auth):
        self.app = app
        self.auth = auth

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        ip = client_ip(scope)
        lim = self.auth.limiter
        if lim.is_blocked(ip):
            return await send_404(scope, receive, send)
        h = _headers(scope)
        qs = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        if scope["type"] == "http" and scope["path"] == "/" and "k" in qs:
            name = self.auth.store.name_for(qs["k"][0][:200])
            if not name:
                lim.fail(ip)
                return await send_404(scope, receive, send)
            cookie = (f"{COOKIE}={self.auth.make_cookie(name)}; Max-Age={COOKIE_MAX_AGE}; Path=/; "
                      f"HttpOnly; Secure; SameSite=Lax")
            await send({"type": "http.response.start", "status": 302,
                        "headers": [(b"location", b"/"), (b"set-cookie", cookie.encode()),
                                    (b"content-length", b"0")] + SEC_HEADERS})
            await send({"type": "http.response.body", "body": b""})
            return
        name = None
        raw = h.get(b"cookie")
        if raw:
            try:
                c = SimpleCookie()
                c.load(raw.decode("latin-1"))
                if COOKIE in c:
                    name = self.auth.check_cookie(c[COOKIE].value)
                    if not name:
                        lim.fail(ip)
            except Exception:
                name = None
        if not name:
            return await send_404(scope, receive, send)
        scope = dict(scope)
        scope["mosca_user"] = name

        if scope["type"] == "http":
            async def send_wrapped(msg):
                if msg["type"] == "http.response.start":
                    hdrs = [(k, v) for k, v in msg.get("headers", []) if k.lower() not in {x for x, _ in SEC_HEADERS}]
                    msg = {**msg, "headers": hdrs + SEC_HEADERS}
                await send(msg)
            return await self.app(scope, receive, send_wrapped)
        return await self.app(scope, receive, send)
