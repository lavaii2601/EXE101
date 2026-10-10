import os
import threading

# Building a Gmail/Calendar service re-reads the token from disk, refreshes
# credentials, and rebuilds the discovery Resource on every call. Reusing the
# instance also keeps the underlying HTTP connection to Google warm instead of
# paying a fresh TCP/TLS handshake on each request.
_lock = threading.Lock()
_cache = {}


def _service_cache_key(token_file, service_kind):
    # Including the calling thread's id keeps each gthread worker thread on
    # its own GmailService/CalendarService instance -- and therefore its own
    # underlying httplib2 Http object and SSL/socket state. httplib2 is not
    # safe for concurrent use of the same instance from multiple threads;
    # sharing one across threads (the previous behavior) let two concurrent
    # requests for the same user corrupt that connection's C-level state,
    # crashing the whole worker process ("double free or corruption") and
    # taking every other in-flight request on it down too. Each thread still
    # reuses its own instance across requests, so the warm-connection intent
    # below is preserved -- it just no longer crosses thread boundaries.
    return (
        os.path.abspath(os.fspath(token_file)),
        str(service_kind or 'default'),
        threading.get_ident(),
    )


def get_cached_service(token_file, factory, service_kind='default'):
    """Return a cached Google API service for a token and service type.

    Gmail and Calendar share the same credentials file, but their discovery
    resources are not interchangeable. Including ``service_kind`` in the key
    prevents a cached GmailService from being returned to Calendar callers (or
    vice versa). Failed authentication attempts are never cached.
    """
    try:
        mtime = os.path.getmtime(token_file)
    except OSError:
        return None

    cache_key = _service_cache_key(token_file, service_kind)
    with _lock:
        cached = _cache.get(cache_key)
        if cached and cached[0] == mtime:
            return cached[1]

    instance = factory()
    if getattr(instance, 'service', None) is not None:
        with _lock:
            _cache[cache_key] = (mtime, instance)
    return instance


def invalidate_cached_service(token_file):
    normalized_token = os.path.abspath(os.fspath(token_file))
    with _lock:
        for cache_key in list(_cache):
            if cache_key[0] == normalized_token:
                _cache.pop(cache_key, None)
