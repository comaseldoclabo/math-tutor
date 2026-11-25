"""Diffusion temps réel (Server-Sent Events) vers les navigateurs connectés.

Implémentation en mémoire : valable pour 1 processus. En multi-processus, remplacer par Redis pub/sub
(même interface : subscribe / unsubscribe / publish).
"""
import asyncio

_subs: dict[int, set] = {}


def subscribe(user_id: int):
    item = (asyncio.get_running_loop(), asyncio.Queue(maxsize=100))
    _subs.setdefault(user_id, set()).add(item)
    return item


def unsubscribe(user_id: int, item) -> None:
    items = _subs.get(user_id)
    if items:
        items.discard(item)
        if not items:
            _subs.pop(user_id, None)


def _put(q: asyncio.Queue, payload: dict) -> None:
    try:
        q.put_nowait(payload)
    except asyncio.QueueFull:
        pass


def publish(user_id: int, payload: dict) -> None:
    """Appelable depuis du code synchrone (threads FastAPI)."""
    for loop, q in list(_subs.get(user_id, ())):
        loop.call_soon_threadsafe(_put, q, payload)
