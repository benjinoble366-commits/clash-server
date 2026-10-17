"""
CLASH online server
===================
Puts two players in a room (one makes it and gets a code, the other types the
code in) and then passes their messages to each other: which fighter they
picked, and the keys they press every frame.  The fight itself runs in both
players' web browsers.

Run it on your own computer for testing:     py server.py
(it listens on port 8765, or on $PORT when a hosting site sets one)
"""

import asyncio
import json
import os
import random
from http import HTTPStatus

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"     # (no I or O: too easy to mix up with 1 and 0)
rooms = {}                              # room code -> the players in it (one or two)


def new_code():
    while True:
        code = "".join(random.choice(LETTERS) for _ in range(4))
        if code not in rooms:
            return code


async def tell(ws, **msg):
    try:
        await ws.send(json.dumps(msg))
    except ConnectionClosed:
        pass


async def player(ws):
    room = None
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            kind = msg.get("t")
            if kind == "create" and room is None:
                room = new_code()
                rooms[room] = [ws]
                print("room", room, "made", flush=True)
                await tell(ws, t="room", code=room)
            elif kind == "join" and room is None:
                code = str(msg.get("code", "")).upper().strip()
                players = rooms.get(code)
                if players is None:
                    await tell(ws, t="error", msg="No room with that code")
                elif len(players) != 1:
                    await tell(ws, t="error", msg="That room is full")
                else:
                    players.append(ws)
                    room = code
                    print("room", room, "full: the fight is on", flush=True)
                    seed = random.randrange(1 << 30)        # both games roll the same dice from this
                    for side, p in enumerate(players):
                        await tell(p, t="start", side=side, seed=seed, code=code)
            elif room is not None:                          # anything else goes to the other player
                for p in rooms.get(room, ()):
                    if p is not ws:
                        try:
                            await p.send(raw)
                        except ConnectionClosed:
                            pass
    except ConnectionClosed:
        pass
    finally:
        if room is not None and room in rooms:
            players = rooms.pop(room)                       # one player gone: the room is over
            print("room", room, "closed", flush=True)
            for p in players:
                if p is not ws:
                    await tell(p, t="left")


def web_page(connection, request):
    """Someone opened the server's address in a normal browser tab (or the host checked it is alive)."""
    if request.headers.get("Upgrade", "").lower() != "websocket":
        return connection.respond(HTTPStatus.OK, "CLASH server is running. Rooms open: %d\n" % len(rooms))
    return None


async def main():
    port = int(os.environ.get("PORT", 8765))
    async with serve(player, "0.0.0.0", port, ping_interval=20, ping_timeout=20, process_request=web_page):
        print("CLASH server running on port", port)
        await asyncio.Future()                              # (run until stopped)


if __name__ == "__main__":
    asyncio.run(main())
