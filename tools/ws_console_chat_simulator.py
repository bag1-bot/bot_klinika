from __future__ import annotations

import asyncio
import json
import os
import random
import signal
import string
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aiohttp import web
from websockets.client import connect
from websockets.exceptions import ConnectionClosed


WS_URL: str = os.getenv("WS_URL", "wss://bot-server.ru/ws/chat/{admin_id}")
ADMIN_ID: str = os.getenv("ADMIN_ID", "admin_1")
TOKEN: str = os.getenv("TOKEN", "CHANGE_ME")

LOCAL_HOST: str = os.getenv("LOCAL_HOST", "127.0.0.1")
LOCAL_PORT: int = int(os.getenv("LOCAL_PORT", "8787"))

PLATFORM: str = os.getenv("PLATFORM", "tg")
PING_INTERVAL_SEC: float = float(os.getenv("PING_INTERVAL_SEC", "20"))
PING_TIMEOUT_SEC: float = float(os.getenv("PING_TIMEOUT_SEC", "10"))


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _rand_user_id() -> str:
    return str(random.randint(100_000_000, 999_999_999))


def _rand_text_tag(n: int = 6) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(n))


@dataclass(slots=True)
class State:
    ws_send_queue: asyncio.Queue[dict[str, Any]]
    active_user_id: str
    user_ids: list[str]
    ai_paused: set[str]


def _auth_ok(request: web.Request) -> bool:
    auth = request.headers.get("Authorization", "")
    return auth == f"Bearer {TOKEN}"


async def _http_send_message(request: web.Request) -> web.Response:
    if not _auth_ok(request):
        return web.json_response({"error": "unauthorized"}, status=401)
    payload = await request.json()
    state: State = request.app["state"]
    action = payload.get("action") or "send_message"
    platform = payload.get("platform") or PLATFORM
    user_id = str(payload.get("user_id") or state.active_user_id)
    text = str(payload.get("text") or "")
    packet = {"action": action, "platform": platform, "user_id": user_id, "text": text}
    await state.ws_send_queue.put(packet)
    print(f"[{_now()}] -> WS (admin): {packet}")
    return web.json_response({"status": "queued"})


async def _http_admin_join(request: web.Request) -> web.Response:
    if not _auth_ok(request):
        return web.json_response({"error": "unauthorized"}, status=401)
    payload = await request.json()
    platform = str(payload.get("platform") or PLATFORM)
    user_id = str(payload.get("user_id") or "")
    admin_id = str(payload.get("admin_id") or ADMIN_ID)
    state: State = request.app["state"]
    if user_id:
        state.ai_paused.add(user_id)
    print(f"[{_now()}] webhook admin_join platform={platform} user_id={user_id} admin_id={admin_id}")
    return web.json_response({"status": "ok"})


async def _start_http_server(state: State) -> web.AppRunner:
    app = web.Application()
    app["state"] = state
    app.router.add_post("/api/send_message", _http_send_message)
    app.router.add_post("/api/webhook/admin_join", _http_admin_join)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, LOCAL_HOST, LOCAL_PORT)
    await site.start()
    print(f"[{_now()}] HTTP server: http://{LOCAL_HOST}:{LOCAL_PORT}")
    return runner


async def _ws_sender(ws, state: State) -> None:
    while True:
        packet = await state.ws_send_queue.get()
        await ws.send(json.dumps(packet, ensure_ascii=False))


async def _ws_receiver(ws) -> None:
    async for raw in ws:
        try:
            data = json.loads(raw)
        except Exception:
            print(f"[{_now()}] <- WS raw: {raw}")
            continue
        print(f"[{_now()}] <- WS: {data}")


async def _ws_pinger(ws) -> None:
    while True:
        await asyncio.sleep(PING_INTERVAL_SEC)
        try:
            pong_waiter = await ws.ping()
            await asyncio.wait_for(pong_waiter, timeout=PING_TIMEOUT_SEC)
            print(f"[{_now()}] ping/pong ok")
        except Exception:
            raise


async def _ws_loop(state: State, stop: asyncio.Event) -> None:
    url = WS_URL.format(admin_id=ADMIN_ID)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    while not stop.is_set():
        try:
            print(f"[{_now()}] connecting ws: {url} as {ADMIN_ID}")
            async with connect(url, extra_headers=headers) as ws:
                print(f"[{_now()}] ws connected")
                tasks = [
                    asyncio.create_task(_ws_sender(ws, state)),
                    asyncio.create_task(_ws_receiver(ws)),
                    asyncio.create_task(_ws_pinger(ws)),
                ]
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
                for t in pending:
                    t.cancel()
                for t in done:
                    exc = t.exception()
                    if exc:
                        raise exc
        except ConnectionClosed as e:
            print(f"[{_now()}] ws closed: {e.code} {e.reason}")
        except Exception as e:
            print(f"[{_now()}] ws error: {type(e).__name__}: {e}")
        if not stop.is_set():
            await asyncio.sleep(2)


def _print_help() -> None:
    print(
        "\n".join(
            [
                "Команды:",
                "  /help                помощь",
                "  /users               список user_id",
                "  /use <user_id>       выбрать активного пользователя",
                "  /new                 создать нового пользователя",
                "  /admin               пометить активного как передан администратору (локально)",
                "  /send <text>         отправить как активный пользователь",
                "  <text>               то же что /send <text>",
                "",
                "HTTP API (тот же Bearer TOKEN):",
                f"  POST http://{LOCAL_HOST}:{LOCAL_PORT}/api/send_message",
                '    {"action":"send_message","platform":"tg","user_id":"123","text":"..."}',
                f"  POST http://{LOCAL_HOST}:{LOCAL_PORT}/api/webhook/admin_join",
                '    {"platform":"tg","user_id":"123","admin_id":"admin_1"}',
            ]
        )
    )


async def _console_loop(state: State, stop: asyncio.Event) -> None:
    _print_help()
    while not stop.is_set():
        line = await asyncio.to_thread(input, f"[{_now()}] > ")
        line = (line or "").strip()
        if not line:
            continue
        if line == "/help":
            _print_help()
            continue
        if line == "/users":
            print(f"active={state.active_user_id} users={state.user_ids}")
            continue
        if line.startswith("/use "):
            user_id = line.split(maxsplit=1)[1].strip()
            if user_id not in state.user_ids:
                state.user_ids.append(user_id)
            state.active_user_id = user_id
            print(f"active user_id={state.active_user_id}")
            continue
        if line == "/new":
            user_id = _rand_user_id()
            state.user_ids.append(user_id)
            state.active_user_id = user_id
            print(f"new user_id={user_id}")
            continue
        if line == "/admin":
            state.ai_paused.add(state.active_user_id)
            print(f"user_id={state.active_user_id} marked waiting admin (local)")
            continue

        if line.startswith("/send "):
            text = line.split(maxsplit=1)[1]
        else:
            text = line

        user_id = state.active_user_id
        packet = {
            "event": "new_message",
            "platform": PLATFORM,
            "user_id": user_id,
            "text": text,
            "meta": {"tag": _rand_text_tag()},
        }
        await state.ws_send_queue.put(packet)
        print(f"[{_now()}] вы написали пользователю {user_id}: {text}")


async def main() -> None:
    random.seed()
    initial_users = [_rand_user_id() for _ in range(3)]
    state = State(
        ws_send_queue=asyncio.Queue(),
        active_user_id=initial_users[0],
        user_ids=initial_users,
        ai_paused=set(),
    )

    stop = asyncio.Event()

    def _handle_stop(*_: object) -> None:
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_stop)
        except Exception:
            pass

    http_runner = await _start_http_server(state)
    try:
        await asyncio.gather(
            _ws_loop(state, stop),
            _console_loop(state, stop),
        )
    finally:
        await http_runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

