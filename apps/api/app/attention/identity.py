"""Anonymous-first profile identity (docs/PLAN.md section 4.1): a signed,
HTTP-only cookie holds a `profile_id` UUID issued on first visit. No email,
no password — HMAC-SHA256 over the raw UUID is enough to stop a client from
forging a cookie for someone else's profile without needing a session store.
"""

import hashlib
import hmac
import uuid

COOKIE_NAME = "amt_profile"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year


def sign(profile_id: uuid.UUID, secret: str) -> str:
    raw = str(profile_id)
    signature = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{signature}"


def verify(cookie_value: str, secret: str) -> uuid.UUID | None:
    raw, _, signature = cookie_value.partition(".")
    if not signature:
        return None
    expected = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None
