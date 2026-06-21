import os
import threading

# Building a Gmail/Calendar service re-reads the token from disk, refreshes
# credentials, and rebuilds the discovery Resource on every call. Reusing the
# instance also keeps the underlying HTTP connection to Google warm instead of
# paying a fresh TCP/TLS handshake on each request.
_lock = threading.Lock()
_cache = {}


def get_cached_service(token_file, factory):
    """Return a cached service instance for `token_file`, rebuilding it only
    when the token file changes (login/logout/reconnect) or nothing is cached
    yet. Failed auth attempts are never cached so the next request retries.
    """
    try:
        mtime = os.path.getmtime(token_file)
    except OSError:
        return None

    with _lock:
        cached = _cache.get(token_file)
        if cached and cached[0] == mtime:
            return cached[1]

    instance = factory()
    if getattr(instance, 'service', None) is not None:
        with _lock:
            _cache[token_file] = (mtime, instance)
    return instance


def invalidate_cached_service(token_file):
    with _lock:
        _cache.pop(token_file, None)
