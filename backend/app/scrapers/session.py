"""Browser-session storage for portals behind 2FA.

The approach, which is the industry-standard one and the only one that holds up:
a human logs in once through a visible browser and passes 2FA by hand; Playwright's
``storage_state`` (cookies + localStorage) is saved; every scheduled run reuses it
until the portal expires it, at which point the run stops and asks for another
manual login.

We do not generate or intercept 2FA codes. If the customer can hand over a TOTP
seed, add a ``pyotp`` step to the login CLI — that is a change to one function, not
to this design.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ScraperSession

logger = logging.getLogger(__name__)

STATUS_OK = "ok"
STATUS_NEEDS_LOGIN = "needs_login"
STATUS_ERROR = "error"


class ScraperSessionStore:
    """Reads and writes the saved browser session for one provider."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _row(self, provider: str) -> ScraperSession | None:
        return (
            await self.session.execute(
                select(ScraperSession).where(ScraperSession.provider == provider)
            )
        ).scalar_one_or_none()

    async def load_storage_state(self, provider: str) -> dict[str, Any] | None:
        row = await self._row(provider)
        if row is None or not row.storage_state:
            return None
        if row.status == STATUS_NEEDS_LOGIN:
            # Keep the stale state on disk for debugging, but do not pretend it works.
            logger.info("session for %s is flagged needs_login", provider)
            return None
        return row.storage_state

    async def save_storage_state(self, provider: str, storage_state: dict[str, Any]) -> None:
        row = await self._row(provider)
        now = datetime.now(UTC)
        if row is None:
            row = ScraperSession(provider=provider)
            self.session.add(row)
        row.storage_state = storage_state
        row.status = STATUS_OK
        row.last_login_at = now
        row.last_error = None
        await self.session.flush()

    async def mark(self, provider: str, status: str, error: str | None = None) -> None:
        row = await self._row(provider)
        if row is None:
            row = ScraperSession(provider=provider)
            self.session.add(row)
        row.status = status
        row.last_error = (error or "")[:500] or None
        await self.session.flush()

    async def status(self, provider: str) -> str:
        row = await self._row(provider)
        return row.status if row else STATUS_NEEDS_LOGIN


def looks_like_login_page(url: str, content: str) -> bool:
    """Heuristic for "the saved session has expired".

    Portals answer an expired session with a redirect to the login form rather
    than an HTTP error, so the only signal is what came back.
    """
    lowered_url = (url or "").lower()
    if any(token in lowered_url for token in ("/login", "/signin", "/auth", "sso")):
        return True
    head = (content or "")[:4000].lower()
    markers = ("type=\"password\"", "type='password'", "two-factor", "verification code")
    return any(marker in head for marker in markers)
