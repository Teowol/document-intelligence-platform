"""Production-grade settings (Phase 9).

Usage:
    DJANGO_SETTINGS_MODULE=config.settings.production python manage.py runserver

This file hardens settings that `manage.py check --deploy` flags. It is NOT the
active default; the learning project runs `config.settings` in development.
Activate it only when actually serving HTTPS behind a reverse proxy.
"""

from config.settings.base import *  # noqa: F401,F403
import json
import logging
# Secure cookies — only when served over HTTPS.
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Strict Transport Security (whole site over SSL).
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Force HTTPS via the reverse proxy / load balancer.
SECURE_SSL_REDIRECT = True

# Let the reverse proxy (nginx) forward X-Forwarded-* headers.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Content cache & XSS guard.
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"


class _JsonFormatter(logging.Formatter):
    """Single-line JSON log records for easy ingestion by log shipping tools.

    Kept dependency-free: no `python-json-logger` needed.
    """

    _FIELDS = ("asctime", "levelname", "name", "module", "message")

    def format(self, record):
        payload = {field: getattr(record, field, None) for field in self._FIELDS}
        payload["level"] = record.levelname
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


# Structured logging: JSON to the console for log collation in production.
LOGGING["formatters"]["json"] = {"()": _JsonFormatter}
LOGGING["handlers"]["console"]["formatter"] = "json"
