"""Server-Sent Events hub for real-time chart updates."""
import json
import queue
import threading

_lock = threading.Lock()
_subscribers: dict[str, list[queue.Queue]] = {}


def subscribe(user_email: str) -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=50)
    with _lock:
        _subscribers.setdefault(user_email, []).append(q)
    return q


def unsubscribe(user_email: str, q: queue.Queue) -> None:
    with _lock:
        subs = _subscribers.get(user_email, [])
        if q in subs:
            subs.remove(q)
        if not subs and user_email in _subscribers:
            del _subscribers[user_email]


def publish(user_email: str, event_type: str, data: dict) -> int:
    payload = json.dumps({'type': event_type, 'data': data})
    delivered = 0
    with _lock:
        subs = list(_subscribers.get(user_email, []))
    for q in subs:
        try:
            q.put_nowait(payload)
            delivered += 1
        except queue.Full:
            pass
    return delivered
