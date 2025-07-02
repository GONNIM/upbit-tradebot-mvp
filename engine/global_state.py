import threading
import time
from typing import Optional


class EngineThreadRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._threads = {}

    def get_all(self):
        with self._lock:
            return self._threads.copy()

    def add_thread(
        self, user_id: str, thread: threading.Thread, stop_event: threading.Event
    ):
        with self._lock:
            self._threads[user_id] = {
                "thread": thread,
                "stop_event": stop_event,
                "status": "running",  # or 'stopped', 'error'
                "last_updated": time.time(),
                "last_event": None,
                "note": "",
            }

    def remove_thread(self, user_id: str):
        with self._lock:
            if user_id in self._threads:
                del self._threads[user_id]

    def get_thread(self, user_id: str):
        with self._lock:
            return self._threads.get(user_id)

    def update_status(self, user_id: str, status: str, note: Optional[str] = None):
        with self._lock:
            if user_id in self._threads:
                self._threads[user_id]["status"] = status
                self._threads[user_id]["last_updated"] = time.time()
                if note:
                    self._threads[user_id]["note"] = note

    def update_event_time(self, user_id: str):
        with self._lock:
            if user_id in self._threads:
                self._threads[user_id]["last_event"] = time.time()

    def is_running(self, user_id: str) -> bool:
        with self._lock:
            return (
                user_id in self._threads and self._threads[user_id]["thread"].is_alive()
            )

    def get_active_user_ids(self):
        with self._lock:
            return [
                uid for uid, info in self._threads.items() if info["thread"].is_alive()
            ]

    def stop_all(self):
        with self._lock:
            for user_id, info in self._threads.items():
                info["stop_event"].set()
            self._threads.clear()


# 🔒 싱글톤 인스턴스
_engine_registry = EngineThreadRegistry()


# ✅ 외부 노출 함수
def get_engine_threads():
    return _engine_registry.get_all()


def add_engine_thread(user_id, thread, stop_event):
    _engine_registry.add_thread(user_id, thread, stop_event)


def remove_engine_thread(user_id):
    _engine_registry.remove_thread(user_id)


def is_engine_really_running(user_id):
    return _engine_registry.is_running(user_id)


def update_engine_status(user_id, status, note=None):
    _engine_registry.update_status(user_id, status, note)


def update_event_time(user_id):
    _engine_registry.update_event_time(user_id)


def stop_all_engines():
    _engine_registry.stop_all()
