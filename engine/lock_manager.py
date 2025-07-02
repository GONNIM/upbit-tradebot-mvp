from threading import Lock


_engine_locks = {}


def get_user_lock(user_id: str) -> Lock:
    if user_id not in _engine_locks:
        _engine_locks[user_id] = Lock()
    return _engine_locks[user_id]
