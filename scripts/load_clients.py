"""Keep N WebSocket clients connected for T seconds against a public URL (impact test, BRIEF 5.6)."""
import argparse, asyncio, json, sys, time
from pathlib import Path
import httpx, websockets
sys.path.insert(0, str(Path(__file__).parent))
from public_check import pin_dns


async def one(url, origin, cookie, stop, counts, i):
    async with websockets.connect(url, origin=origin, additional_headers={"cookie": cookie}, max_size=2**20) as ws:
        while time.time() < stop:
            try:
                await asyncio.wait_for(ws.recv(), 3)
                counts[i] += 1
            except asyncio.TimeoutError:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True); ap.add_argument("--token", required=True)
    ap.add_argument("--clients", type=int, default=2); ap.add_argument("--seconds", type=float, default=60)
    a = ap.parse_args()
    base = a.url.rstrip("/"); pin_dns(base.split("//", 1)[1])
    cookie = httpx.get(base + "/?k=" + a.token, follow_redirects=False, timeout=20).headers["set-cookie"].split(";")[0]
    counts = [0] * a.clients
    stop = time.time() + a.seconds
    async def run():
        await asyncio.gather(*[one(base.replace("https", "wss", 1) + "/ws", base, cookie, stop, counts, i) for i in range(a.clients)])
    asyncio.run(run())
    print(json.dumps({"clients": a.clients, "seconds": a.seconds, "fps_per_client": [round(c / a.seconds, 1) for c in counts]}))


if __name__ == "__main__":
    main()
