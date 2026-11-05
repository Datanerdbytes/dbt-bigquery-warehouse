# utils/cache.py
from flask_caching import Cache

# The cache lives in process memory: the deployment target ships a read-only
# filesystem, so a file-backed cache cannot be written there.
cache = Cache(
    config={
        "CACHE_TYPE": "SimpleCache",
        "CACHE_DEFAULT_TIMEOUT": 3600,
    }
)
