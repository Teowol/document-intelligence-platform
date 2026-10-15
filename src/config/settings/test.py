"""Test settings: inherit everything, speed up password hashing, use in-memory
cache so tests never depend on a live Redis."""

from config.settings.base import *  # noqa: F401,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-cache",
    }
}
