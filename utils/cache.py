# utils/cache.py
import os
from flask_caching import Cache

def create_cache():
    """Create cache with Redis in production, FileSystemCache in development."""
    redis_url = os.environ.get("REDIS_URL")
    cache_dir = "cache-directory"
    
    if redis_url:
        # Production configuration - use Redis
        return Cache(
            config={
                "CACHE_TYPE": "RedisCache",
                "CACHE_REDIS_URL": redis_url,
                "CACHE_KEY_PREFIX": "kilo-dash-",
                "CACHE_DEFAULT_TIMEOUT": 3600
            }
        )
    else:
        # Development configuration - fallback to FileSystemCache
        return Cache(
            config={
                "CACHE_TYPE": "FileSystemCache",
                "CACHE_DIR": cache_dir,
                "CACHE_DEFAULT_TIMEOUT": 3600
            }
        )

# Initialize cache
from flask import Flask

def init_app(app: Flask):
    """Initialize cache with the Flask app."""
    app.cache = create_cache()
    return app

cache = create_cache()
