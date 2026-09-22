"""Performance (BRIEF 4.2): N simulated clients for T seconds against a running server.
Reports tick ms p50/p95 (server side) and CPU % of one core of the server process (sampled with ps).
  uv run python scripts/perf.py --base http://127.0.0.1:8765 --clients 10 --seconds 30
"""
import argparse, asyncio, json, subprocess, sys, time
from pathlib import Path
import httpx, websockets

ROOT = Path(__file__).resolve().parents[1]


async def client(url, origin, cookie, stop, counts, i):
    async with websockets.connect(url, origin=origin, additional_headers={"cookie": cookie}, max_size=2**20) as ws:
        while time.time() < stop:
            try:
                await asyncio.wait_for(ws.recv(), 2)
                counts[i] += 1
            except asyncio.TimeoutError:
                pass


def cpu_of(pid):
    out = subprocess.run(["ps", "-o", "%cpu=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    ap.add_argument("--clients", type=int, default=10)
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--token", default=None)
    ap.add_argument("--pid", type=int, default=None)
    a = ap.parse_args()
    tok = a.token or (ROOT / "tmp/local-secrets/tokens.yaml").read_text().splitlines()[0].split(":", 1)[1].strip()
    r = httpx.get(f"{a.base}/?k={tok}", follow_redirects=False)
    cookie = r.headers["set-cookie"].split(";")[0]
    ws_url = a.base.replace("http", "ws", 1) + "/ws"
    pid = a.pid
    if pid is None:
        port = a.base.rsplit(":", 1)[1]
        pid = int(subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"], capture_output=True, text=True).stdout.split()[0])
    idle = [cpu_of(pid) for _ in range(3)]
    counts = [0] * a.clients
    stop = time.time() + a.seconds

    async def run():
        tasks = [asyncio.create_task(client(ws_url, a.base, cookie, stop, counts, i)) for i in range(a.clients)]
        samples = []
        await asyncio.sleep(3)
        while time.time() < stop - 1:
            samples.append(cpu_of(pid))
            await asyncio.sleep(1)
        h = httpx.get(f"{a.base}/health-internal", headers={"cookie": cookie}).json()
        await asyncio.gather(*tasks, return_exceptions=True)
        return samples, h

    samples, h = asyncio.run(run())
    res = {"clients": a.clients, "seconds": a.seconds, "frames_per_client_per_s": round(sum(counts) / a.clients / a.seconds, 1),
           "tick_ms_p50": round(h["tick_ms_p50"], 3), "tick_ms_p95": round(h["tick_ms_p95"], 3),
           "cpu_pct_one_core_mean": round(sum(samples) / max(len(samples), 1), 1), "cpu_pct_idle_before": idle}
    print(json.dumps(res))
    return res


if __name__ == "__main__":
    main()
