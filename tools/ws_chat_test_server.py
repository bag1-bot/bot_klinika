from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web


def _load_tools_env_file() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    p = Path(__file__).resolve().parent / ".env"
    if p.is_file():
        load_dotenv(p, override=False)


_load_tools_env_file()


HOST: str = os.getenv("HOST", "127.0.0.1")
PORT: int = int(os.getenv("PORT", "8001"))
TOKEN: str = os.getenv("TOKEN", "CHANGE_ME")


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _auth_ok(request: web.Request) -> bool:
    auth = request.headers.get("Authorization", "")
    return auth == f"Bearer {TOKEN}"


@dataclass(slots=True)
class Hub:
    conns: dict[str, set[web.WebSocketResponse]]
    lock: asyncio.Lock

    async def add(self, admin_id: str, ws: web.WebSocketResponse) -> None:
        async with self.lock:
            self.conns.setdefault(admin_id, set()).add(ws)

    async def remove(self, admin_id: str, ws: web.WebSocketResponse) -> None:
        async with self.lock:
            if admin_id in self.conns:
                self.conns[admin_id].discard(ws)
                if not self.conns[admin_id]:
                    self.conns.pop(admin_id, None)

    async def broadcast(self, admin_id: str, payload: dict[str, Any]) -> int:
        data = json.dumps(payload, ensure_ascii=False)
        async with self.lock:
            targets = list(self.conns.get(admin_id, set()))
        sent = 0
        for ws in targets:
            if ws.closed:
                continue
            try:
                await ws.send_str(data)
                sent += 1
            except Exception:
                continue
        return sent


async def ws_chat(request: web.Request) -> web.StreamResponse:
    if not _auth_ok(request):
        return web.json_response({"error": "unauthorized"}, status=401)

    admin_id = request.match_info.get("admin_id", "")
    if not admin_id:
        return web.json_response({"error": "admin_id_required"}, status=400)

    ws = web.WebSocketResponse(heartbeat=20.0)
    await ws.prepare(request)

    hub: Hub = request.app["hub"]
    await hub.add(admin_id, ws)
    print(f"[{_now()}] ws connected admin_id={admin_id}")

    await hub.broadcast(admin_id, {"event": "connected", "admin_id": admin_id})

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                raw = msg.data
                try:
                    data = json.loads(raw)
                except Exception:
                    await ws.send_str(json.dumps({"event": "error", "error": "invalid_json"}, ensure_ascii=False))
                    continue

                print(f"[{_now()}] <- ws admin_id={admin_id}: {data}")

                if isinstance(data, dict) and data.get("action") == "send_message":
                    ack = {
                        "event": "send_message_ack",
                        "ok": True,
                        "platform": data.get("platform"),
                        "user_id": data.get("user_id"),
                        "text": data.get("text"),
                    }
                    await ws.send_str(json.dumps(ack, ensure_ascii=False))
                elif isinstance(data, dict) and data.get("event") == "new_message":
                    forward = {
                        "event": "new_message",
                        "platform": data.get("platform"),
                        "user_id": data.get("user_id"),
                        "text": data.get("text"),
                    }
                    await hub.broadcast(admin_id, forward)
                else:
                    await ws.send_str(json.dumps({"event": "unknown_packet", "data": data}, ensure_ascii=False))

            elif msg.type == WSMsgType.ERROR:
                print(f"[{_now()}] ws error admin_id={admin_id}: {ws.exception()}")
                break
    finally:
        await hub.remove(admin_id, ws)
        print(f"[{_now()}] ws disconnected admin_id={admin_id}")

    return ws


async def http_send_message(request: web.Request) -> web.Response:
    if not _auth_ok(request):
        return web.json_response({"error": "unauthorized"}, status=401)
    payload = await request.json()
    admin_id = str(payload.get("admin_id") or "")
    if not admin_id:
        return web.json_response({"error": "admin_id_required"}, status=400)
    hub: Hub = request.app["hub"]
    sent = await hub.broadcast(admin_id, payload)
    return web.json_response({"status": "ok", "sent": sent})


async def webhook_admin_join(request: web.Request) -> web.Response:
    if not _auth_ok(request):
        return web.json_response({"error": "unauthorized"}, status=401)
    payload = await request.json()
    print(f"[{_now()}] webhook admin_join: {payload}")
    admin_id = str(payload.get("admin_id") or "")
    if admin_id:
        hub: Hub = request.app["hub"]
        await hub.broadcast(admin_id, {"event": "admin_join", **payload})
    return web.json_response({"status": "ok"})


def create_app() -> web.Application:
    app = web.Application()
    app["hub"] = Hub(conns={}, lock=asyncio.Lock())
    app.router.add_get("/ws/chat/{admin_id}", ws_chat)
    app.router.add_post("/api/send_message", http_send_message)
    app.router.add_post("/api/webhook/admin_join", webhook_admin_join)
    return app


def main() -> None:
    app = create_app()
    web.run_app(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()

