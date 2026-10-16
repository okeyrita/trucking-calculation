"""One-off manual login for portals behind 2FA.

Run it on a machine with a display (or over X/VNC), log in as a human, pass the
2FA challenge, then press Enter. The resulting browser session is stored in the
database and reused by the scheduled refresh until the portal expires it.

    python -m app.scrapers.login_cli --provider contract_portal

This is the only step that needs a person, and it is needed roughly as often as
the portal's session lifetime — typically weeks.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.core.config import get_settings
from app.core.db import session_scope
from app.scrapers.session import ScraperSessionStore


async def run(provider: str, url: str | None, headless: bool) -> int:
    settings = get_settings()
    target = url or settings.contract_portal_url
    if not target:
        print(
            "No URL to open. Pass --url or set CONTRACT_PORTAL_URL in .env",
            file=sys.stderr,
        )
        return 2

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print(
            "Playwright is missing. Install it with:\n"
            "    pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return 3

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(target)

        print(f"\nA browser window is open at {target}")
        print("Log in and complete the 2FA challenge, then come back here.")
        if settings.contract_portal_username:
            print(f"Username on file: {settings.contract_portal_username}")
        # Blocking input in a thread keeps the browser's event loop responsive.
        await asyncio.get_running_loop().run_in_executor(
            None, input, "\nPress Enter once you are fully logged in... "
        )

        storage_state = await context.storage_state()
        await context.close()
        await browser.close()

    async with session_scope() as session:
        await ScraperSessionStore(session).save_storage_state(provider, storage_state)
        await session.commit()

    cookies = len(storage_state.get("cookies", []))
    print(f"\nSaved session for {provider!r}: {cookies} cookies stored in the database.")
    print("Scheduled refreshes will reuse it until the portal expires it.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="contract_portal")
    parser.add_argument("--url", default=None, help="overrides CONTRACT_PORTAL_URL")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="only useful for smoke-testing the plumbing; you cannot pass 2FA blind",
    )
    args = parser.parse_args()
    return asyncio.run(run(args.provider, args.url, args.headless))


if __name__ == "__main__":
    raise SystemExit(main())
